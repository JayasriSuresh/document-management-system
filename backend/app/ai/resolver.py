"""
Module 10 — AI Configuration Hierarchy Resolver.

Enforces the strict multi-tier configuration governance:
  Platform (Master Admin) -> Company (Company Admin) -> Branch (Branch Admin)

Precedence & Invariants:
- Platform settings dictate global provider availability and model allow-lists.
- Company settings narrow permitted providers and enforce company AI consent.
- Branch settings select operation-specific providers and models (read vs generate).
- A branch cannot select a provider disallowed by its company.
- A company cannot select a provider disabled by the platform.
- An unconsented provider cannot be invoked under any circumstances.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models import (
    Company, Branch, PlatformAIProvider, CompanyAISetting,
    CompanyAIConsent, BranchAIConfig, AICredential,
    AIModelCatalogue, CompanyAIModelAssignment
)
from app.ai.base import AIProviderError
from app.security.encryption import decrypt_api_key
from app.config import settings


@dataclass
class ResolvedProviderDetails:
    provider_key: str
    model: str
    api_key: str
    credential_source: str  # 'branch', 'company', 'platform', 'env'
    max_retries: int = 2
    timeout_seconds: int = 30


@dataclass
class ResolvedAIConfig:
    company_id: int
    branch_id: int
    operation: str
    primary: ResolvedProviderDetails
    fallback: Optional[ResolvedProviderDetails] = None


def resolve_credential(
    db: Session,
    provider_key: str,
    company_id: int,
    branch_id: int,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve API key in deterministic precedence order:
      Branch Credential -> Company Credential -> Platform Credential -> Environment Default
    Returns (decrypted_api_key, credential_source) or (None, None).
    """
    # 1. Branch scope
    branch_cred = (
        db.query(AICredential)
        .filter(
            AICredential.provider_key == provider_key,
            AICredential.scope_type == "branch",
            AICredential.scope_id == branch_id,
            AICredential.status == "active",
        )
        .first()
    )
    if branch_cred:
        try:
            return decrypt_api_key(branch_cred.encrypted_key), "branch"
        except Exception:
            pass

    # 2. Company scope
    comp_cred = (
        db.query(AICredential)
        .filter(
            AICredential.provider_key == provider_key,
            AICredential.scope_type == "company",
            AICredential.scope_id == company_id,
            AICredential.status == "active",
        )
        .first()
    )
    if comp_cred:
        try:
            return decrypt_api_key(comp_cred.encrypted_key), "company"
        except Exception:
            pass

    # 3. Platform scope
    plat_cred = (
        db.query(AICredential)
        .filter(
            AICredential.provider_key == provider_key,
            AICredential.scope_type == "platform",
            AICredential.status == "active",
        )
        .first()
    )
    if plat_cred:
        try:
            return decrypt_api_key(plat_cred.encrypted_key), "platform"
        except Exception:
            pass

    # 4. Environment default (for backward-compatible development / fallback)
    if provider_key == "gemini" and getattr(settings, "GEMINI_API_KEY", None):
        return settings.GEMINI_API_KEY, "env"
    if provider_key == "openai" and getattr(settings, "OPENAI_API_KEY", None):
        return settings.OPENAI_API_KEY, "env"
    if provider_key == "anthropic" and getattr(settings, "ANTHROPIC_API_KEY", None):
        return settings.ANTHROPIC_API_KEY, "env"

    return None, None


def resolve_ai_config(
    db: Session,
    company_id: int,
    branch_id: int,
    operation: str,
) -> ResolvedAIConfig:
    """
    Authoritative AI configuration resolution.
    Validates company status, branch tenancy, platform availability, company allow-list,
    explicit company consent, model allow-lists, and credentials.
    """
    # 1. Verify Company
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise AIProviderError("COMPANY_NOT_FOUND", f"Company #{company_id} does not exist.", is_retryable=False)
    if (company.status or "").lower() == "suspended":
        raise AIProviderError("COMPANY_SUSPENDED", "Cannot execute AI operations for a suspended company.", is_retryable=False)

    # 1.1 Verify Company AI Access is enabled
    comp_setting = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company_id).first()
    if comp_setting and hasattr(comp_setting, "is_ai_enabled") and not comp_setting.is_ai_enabled:
        raise AIProviderError("AI_ACCESS_DISABLED", f"AI operations are disabled for Company #{company_id} by platform administrator.", is_retryable=False)

    # 2. Verify Branch
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not branch:
        raise AIProviderError("BRANCH_NOT_FOUND", f"Branch #{branch_id} does not belong to Company #{company_id}.", is_retryable=False)
    if hasattr(branch, "status") and (branch.status or "").lower() == "inactive":
        raise AIProviderError("BRANCH_INACTIVE", f"Branch #{branch_id} is deactivated.", is_retryable=False)
    if hasattr(branch, "is_active") and not branch.is_active:
        raise AIProviderError("BRANCH_INACTIVE", f"Branch #{branch_id} is deactivated.", is_retryable=False)

    # 3. Resolve Master Admin Company Model Assignment
    # Map operation string to task_type: 'ocr', 'extraction', 'generation'
    task_keys = [operation]
    if operation in ("read", "ocr"):
        task_keys = ["ocr", "read"]
    elif operation in ("extraction",):
        task_keys = ["extraction", "ocr", "read"]
    elif operation in ("generate", "generation", "invoice_generation"):
        task_keys = ["generation", "generate"]

    assignment = None
    for tk in task_keys:
        assignment = (
            db.query(CompanyAIModelAssignment)
            .filter(
                CompanyAIModelAssignment.company_id == company_id,
                CompanyAIModelAssignment.task_type == tk,
                CompanyAIModelAssignment.is_enabled == True,
            )
            .order_by(CompanyAIModelAssignment.id.desc())
            .first()
        )
        if assignment:
            break

    allowed_providers = comp_setting.allowed_providers if comp_setting and comp_setting.allowed_providers else ["gemini", "openai", "anthropic"]

    if assignment:
        primary_provider = assignment.provider_key
        primary_model = assignment.model_id
        fallback_provider = None
        fallback_model = None
        max_retries = 2
        timeout_seconds = 30
    else:
        # Check branch config or company defaults (with fallback compatibility)
        branch_op_keys = [operation]
        if operation in ("read", "ocr", "extraction"):
            branch_op_keys = [operation, "read", "ocr"]
        elif operation in ("generate", "generation", "invoice_generation"):
            branch_op_keys = [operation, "generate", "generation"]

        branch_cfg = None
        for bok in branch_op_keys:
            branch_cfg = (
                db.query(BranchAIConfig)
                .filter(
                    BranchAIConfig.company_id == company_id,
                    BranchAIConfig.branch_id == branch_id,
                    BranchAIConfig.operation == bok,
                )
                .first()
            )
            if branch_cfg:
                break
        if branch_cfg:
            primary_provider = branch_cfg.primary_provider
            primary_model = branch_cfg.primary_model
            fallback_provider = branch_cfg.fallback_provider
            fallback_model = branch_cfg.fallback_model
            max_retries = branch_cfg.max_retries
            timeout_seconds = branch_cfg.timeout_seconds
        elif comp_setting:
            if operation in ("generate", "generation") and comp_setting.default_generate_provider:
                primary_provider = comp_setting.default_generate_provider
                primary_model = comp_setting.default_generate_model or "gemini-3.6-flash"
            elif comp_setting.default_read_provider:
                primary_provider = comp_setting.default_read_provider
                primary_model = comp_setting.default_read_model or "gemini-3.6-flash"
            else:
                primary_provider = "gemini"
                primary_model = "gemini-3.6-flash"
            fallback_provider = None
            fallback_model = None
            max_retries = 2
            timeout_seconds = 30
        else:
            raise AIProviderError(
                "AI_CAPABILITY_NOT_ENABLED",
                f"No approved AI model assignment configured for task '{operation}' for Company #{company_id}.",
                is_retryable=False,
            )

    # 4. Validate Primary Provider against Platform Availability
    plat_primary = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == primary_provider).first()
    if not plat_primary or not plat_primary.is_enabled:
        raise AIProviderError("AI_PROVIDER_DISABLED", f"AI provider '{primary_provider}' is disabled platform-wide.", is_retryable=False)

    # 5. Validate Primary Model against Platform Catalogue and Allow-List
    cat_model = (
        db.query(AIModelCatalogue)
        .filter(
            AIModelCatalogue.provider_key == primary_provider,
            AIModelCatalogue.model_id == primary_model,
        )
        .first()
    )
    if cat_model and not cat_model.is_active:
        raise AIProviderError("AI_MODEL_DISABLED", f"Model '{primary_model}' is deactivated in the platform catalogue.", is_retryable=False)

    if plat_primary.model_allow_list and primary_model not in plat_primary.model_allow_list:
        raise AIProviderError("AI_MODEL_NOT_ALLOWED", f"Model '{primary_model}' is not permitted for provider '{primary_provider}'.", is_retryable=False)

    # 6. Validate Primary Provider against Company Permissions
    if primary_provider not in allowed_providers:
        raise AIProviderError("AI_PROVIDER_DISALLOWED", f"Company has not permitted AI provider '{primary_provider}'.", is_retryable=False)

    # 7. Validate Explicit Company Consent for Primary Provider
    consent_rec = (
        db.query(CompanyAIConsent)
        .filter(
            CompanyAIConsent.company_id == company_id,
            CompanyAIConsent.provider_key == primary_provider,
            CompanyAIConsent.is_consented == True,
        )
        .first()
    )
    if not consent_rec:
        raise AIProviderError(
            "AI_CONSENT_REQUIRED",
            f"Company consent has not been granted for AI provider '{primary_provider}'. External processing blocked.",
            is_retryable=False,
        )

    # 8. Resolve Primary Credential
    primary_key, primary_src = resolve_credential(db, primary_provider, company_id, branch_id)
    if not primary_key:
        raise AIProviderError(
            "AI_INVALID_CREDENTIALS",
            f"No active API credential configured for AI provider '{primary_provider}'.",
            is_retryable=False,
        )

    primary_details = ResolvedProviderDetails(
        provider_key=primary_provider,
        model=primary_model,
        api_key=primary_key,
        credential_source=primary_src or "unknown",
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
    )

    # 9. Validate Fallback Provider (if specified)
    fallback_details = None
    if fallback_provider and fallback_provider != primary_provider:
        plat_fallback = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == fallback_provider).first()
        if plat_fallback and plat_fallback.is_enabled and fallback_provider in allowed_providers:
            # Check consent for fallback provider
            fallback_consent = (
                db.query(CompanyAIConsent)
                .filter(
                    CompanyAIConsent.company_id == company_id,
                    CompanyAIConsent.provider_key == fallback_provider,
                    CompanyAIConsent.is_consented == True,
                )
                .first()
            )
            if fallback_consent:
                # Check model
                fb_model = fallback_model or (plat_fallback.model_allow_list[0] if plat_fallback.model_allow_list else "")
                if not plat_fallback.model_allow_list or fb_model in plat_fallback.model_allow_list:
                    fb_key, fb_src = resolve_credential(db, fallback_provider, company_id, branch_id)
                    if fb_key:
                        fallback_details = ResolvedProviderDetails(
                            provider_key=fallback_provider,
                            model=fb_model,
                            api_key=fb_key,
                            credential_source=fb_src or "unknown",
                            max_retries=1,
                            timeout_seconds=timeout_seconds,
                        )

    return ResolvedAIConfig(
        company_id=company_id,
        branch_id=branch_id,
        operation=operation,
        primary=primary_details,
        fallback=fallback_details,
    )
