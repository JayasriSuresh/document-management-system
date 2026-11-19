"""
Module 10 — Multi-Provider AI Administration and Configuration APIs.

Endpoints:
1. Platform AI Router (/api/admin/ai):
   - GET /providers: Catalogue and model allow-lists (Master Admin)
   - PUT /providers/{provider_key}: Enable/disable and allow-list update
   - GET /credentials: Platform-level credentials (masked)
   - POST /credentials: Save encrypted platform credential (write-only)
   - DELETE /credentials/{credential_id}: Revoke platform credential
   - POST /test-connection: Safe connection test for platform

2. Company AI Router (/api/company/ai):
   - GET /settings: Allowed providers, defaults, consent status, budget info
   - PUT /settings: Update permitted providers and company defaults
   - POST /consent: Grant explicit company consent for provider
   - POST /consent/revoke: Revoke consent for provider
   - GET /credentials: Company-scoped credentials (masked)
   - POST /credentials: Save encrypted company credential (write-only)
   - DELETE /credentials/{credential_id}: Revoke company credential
   - GET /usage: Attempt-level logs and aggregated token/cost metrics

3. Branch AI Router (/api/company/branches/{branch_id}/ai):
   - GET /config: Get branch operation configs (read & generate)
   - PUT /config: Upsert operation-specific provider/model configuration
   - POST /test-connection: Test connection with branch/company credential
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.currency_service import get_usd_to_inr_rate
from app.context import AuthContext, MasterAdminContext
from app.auth.dependencies import (
    require_permission,
    requires,
)
from app.auth.permissions import (
    PLATFORM_MANAGE,
    AI_SETTINGS_VIEW,
    AI_SETTINGS_MANAGE,
    AI_USAGE_VIEW,
)
from app.models import (
    Company, Branch, PlatformAIProvider, CompanyAISetting,
    CompanyAIConsent, BranchAIConfig, AICredential, AIProcessingLog
)
from app.security.encryption import (
    encrypt_api_key, decrypt_api_key, mask_api_key
)
from app.ai.service import AIExecutionService
from app.ai.base import AIProviderError
from app.audit import (
    audit,
    AI_CONFIG_UPDATE,
    AI_CREDENTIAL_CREATE,
    AI_CREDENTIAL_DELETE,
    AI_CONSENT_GRANT,
    AI_CONSENT_REVOKE,
    AI_CONNECTION_TEST,
)

logger = logging.getLogger("dms.ai.api")

platform_ai_router = APIRouter(prefix="/api/admin/ai", tags=["Platform AI"])
company_ai_router = APIRouter(prefix="/api/company/ai", tags=["Company AI"])
branch_ai_router = APIRouter(prefix="/api/company/branches", tags=["Branch AI"])


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class PlatformProviderOut(BaseModel):
    id: int
    provider_key: str
    display_name: str
    is_enabled: bool
    model_allow_list: List[str]
    supported_operations: List[str]

    class Config:
        from_attributes = True


class PlatformProviderUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    model_allow_list: Optional[List[str]] = None


class CredentialCreate(BaseModel):
    provider_key: str = Field(..., min_length=2, max_length=32)
    api_key: str = Field(..., min_length=4)


class CredentialOut(BaseModel):
    id: int
    provider_key: str
    scope_type: str
    scope_id: Optional[int]
    masked_key: str
    status: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class ConnectionTestRequest(BaseModel):
    provider_key: str
    model: str
    api_key: Optional[str] = None


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: int


class CompanyAISettingsOut(BaseModel):
    company_id: int
    allowed_providers: List[str]
    default_read_provider: Optional[str]
    default_read_model: Optional[str]
    default_generate_provider: Optional[str]
    default_generate_model: Optional[str]
    consents: List[Dict[str, Any]]
    budget: Dict[str, Any]
    platform_providers: List[PlatformProviderOut]


class CompanyAISettingsUpdate(BaseModel):
    allowed_providers: Optional[List[str]] = None
    default_read_provider: Optional[str] = None
    default_read_model: Optional[str] = None
    default_generate_provider: Optional[str] = None
    default_generate_model: Optional[str] = None


class ConsentRequest(BaseModel):
    provider_key: str
    policy_version: Optional[str] = "1.0"
    consented_terms_version: Optional[str] = None


class RevokeConsentRequest(BaseModel):
    provider_key: str


class BranchAIConfigIn(BaseModel):
    operation: str = Field(..., pattern="^(read|generate)$")
    primary_provider: str
    primary_model: str
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    max_retries: int = Field(2, ge=0, le=5)
    timeout_seconds: int = Field(30, ge=5, le=120)


class BranchAIConfigOut(BaseModel):
    id: int
    company_id: int
    branch_id: int
    operation: str
    primary_provider: str
    primary_model: str
    fallback_provider: Optional[str]
    fallback_model: Optional[str]
    max_retries: int
    timeout_seconds: int

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# 1. PLATFORM AI ENDPOINTS (Master Admin)
# ─────────────────────────────────────────────────────────────────────────────

@platform_ai_router.get("/providers", response_model=List[PlatformProviderOut])
def list_platform_providers(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """List all AI providers and model allow-lists available on the platform."""
    providers = db.query(PlatformAIProvider).order_by(PlatformAIProvider.id.asc()).all()
    return providers


@platform_ai_router.put("/providers/{provider_key}", response_model=PlatformProviderOut)
def update_platform_provider(
    provider_key: str,
    payload: PlatformProviderUpdate,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Enable/disable an AI provider or update its platform model allow-list."""
    provider = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == provider_key).first()
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_key}' not found.")

    if payload.is_enabled is not None:
        provider.is_enabled = payload.is_enabled
    if payload.model_allow_list is not None:
        provider.model_allow_list = payload.model_allow_list

    db.commit()
    db.refresh(provider)

    audit.record(
        db=db,
        action=AI_CONFIG_UPDATE,
        actor_type="master_admin",
        actor_id=admin_ctx.admin_id if hasattr(admin_ctx, "admin_id") else getattr(admin_ctx, "user_id", None),
        object_type="ai_provider",
        object_id=provider.id,
        metadata={"description": f"Updated AI provider '{provider_key}': enabled={provider.is_enabled}, models={provider.model_allow_list}"},
    )
    return provider


@platform_ai_router.get("/credentials", response_model=List[CredentialOut])
def list_platform_credentials(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """List platform-level AI credentials (write-only: returns masked keys)."""
    creds = db.query(AICredential).filter(AICredential.scope_type == "platform").all()
    results = []
    for c in creds:
        try:
            plain = decrypt_api_key(c.encrypted_key)
            masked = mask_api_key(plain)
        except Exception:
            masked = "••••••••"
        results.append(CredentialOut(
            id=c.id,
            provider_key=c.provider_key,
            scope_type=c.scope_type,
            scope_id=c.scope_id,
            masked_key=masked,
            status=c.status,
            created_at=c.created_at,
        ))
    return results


@platform_ai_router.post("/credentials", response_model=CredentialOut)
def create_platform_credential(
    payload: CredentialCreate,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Save encrypted platform-level AI credential (write-only)."""
    enc_key = encrypt_api_key(payload.api_key.strip())
    masked = mask_api_key(payload.api_key.strip())
    existing = (
        db.query(AICredential)
        .filter(AICredential.scope_type == "platform", AICredential.provider_key == payload.provider_key)
        .first()
    )
    if existing:
        existing.encrypted_key = enc_key
        existing.masked_key = masked
        existing.status = "active"
        existing.updated_at = datetime.utcnow()
        cred = existing
    else:
        cred = AICredential(
            provider_key=payload.provider_key,
            scope_type="platform",
            scope_id=None,
            encrypted_key=enc_key,
            masked_key=masked,
            status="active",
        )
        db.add(cred)

    db.commit()
    db.refresh(cred)

    audit.record(
        db=db,
        action=AI_CREDENTIAL_CREATE,
        actor_type="master_admin",
        actor_id=admin_ctx.admin_id if hasattr(admin_ctx, "admin_id") else getattr(admin_ctx, "user_id", None),
        object_type="ai_credential",
        object_id=cred.id,
        metadata={"description": f"Saved encrypted platform credential for provider '{payload.provider_key}'"},
    )

    return CredentialOut(
        id=cred.id,
        provider_key=cred.provider_key,
        scope_type=cred.scope_type,
        scope_id=cred.scope_id,
        masked_key=mask_api_key(payload.api_key.strip()),
        status=cred.status,
        created_at=cred.created_at,
    )


@platform_ai_router.delete("/credentials/{credential_id}")
def delete_platform_credential(
    credential_id: int,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Delete a platform credential."""
    cred = db.query(AICredential).filter(AICredential.id == credential_id, AICredential.scope_type == "platform").first()
    if not cred:
        raise HTTPException(status_code=404, detail="Platform credential not found.")
    db.delete(cred)
    db.commit()

    audit.record(
        db=db,
        action=AI_CREDENTIAL_DELETE,
        actor_type="master_admin",
        actor_id=admin_ctx.admin_id if hasattr(admin_ctx, "admin_id") else getattr(admin_ctx, "user_id", None),
        object_type="ai_credential",
        object_id=credential_id,
        metadata={"description": f"Deleted platform credential #{credential_id} for '{cred.provider_key}'"},
    )
    return {"message": "Credential deleted successfully"}


@platform_ai_router.post("/test-connection", response_model=ConnectionTestResponse)
def test_platform_connection(
    payload: ConnectionTestRequest,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Test AI provider connection at platform scope without customer data."""
    success, msg, latency = AIExecutionService.test_provider_connection(
        db=db,
        provider_key=payload.provider_key,
        model=payload.model,
        api_key=payload.api_key,
        actor_user_id=admin_ctx.user_id if hasattr(admin_ctx, "user_id") else None,
    )
    return ConnectionTestResponse(success=success, message=msg, latency_ms=latency)


# ─────────────────────────────────────────────────────────────────────────────
# 2. COMPANY AI ENDPOINTS (Company Admin)
# ─────────────────────────────────────────────────────────────────────────────

@company_ai_router.get("/settings", response_model=CompanyAISettingsOut)
def get_company_ai_settings(
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """Get company AI configuration, consents, budgets, and available platform providers."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    comp_setting = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company_id).first()
    allowed_providers = comp_setting.allowed_providers if comp_setting and comp_setting.allowed_providers else ["gemini", "openai", "anthropic"]

    consents_db = db.query(CompanyAIConsent).filter(CompanyAIConsent.company_id == company_id).all()
    consents_list = [
        {
            "provider_key": c.provider_key,
            "is_consented": c.is_consented,
            "consented_at": c.consented_at.isoformat() if c.consented_at else None,
            "consented_by": c.consented_by,
            "terms_version": getattr(c, "policy_version", "1.0"),
        }
        for c in consents_db
    ]

    plat_providers = db.query(PlatformAIProvider).order_by(PlatformAIProvider.id.asc()).all()

    rate = get_usd_to_inr_rate(db)
    budget_inr = (
        float(company.monthly_ai_budget_inr)
        if company.monthly_ai_budget_inr is not None
        else round(((company.monthly_ai_budget_cents or 5000) / 100.0) * rate, 2)
    )
    spent_inr = float(company.ai_budget_spent_inr or 0.0)

    return CompanyAISettingsOut(
        company_id=company_id,
        allowed_providers=allowed_providers,
        default_read_provider=comp_setting.default_read_provider if comp_setting else "gemini",
        default_read_model=comp_setting.default_read_model if comp_setting else "gemini-2.0-flash",
        default_generate_provider=comp_setting.default_generate_provider if comp_setting else "gemini",
        default_generate_model=comp_setting.default_generate_model if comp_setting else "gemini-2.0-flash",
        consents=consents_list,
        budget={
            "monthly_ai_budget_cents": company.monthly_ai_budget_cents or 5000,
            "ai_budget_spent_cents": company.ai_budget_spent_cents or 0,
            "monthly_ai_budget_inr": budget_inr,
            "ai_budget_spent_inr": spent_inr,
            "reporting_currency": company.reporting_currency or "INR",
            "exchange_rate": rate,
        },
        platform_providers=[PlatformProviderOut.from_orm(p) for p in plat_providers],
    )


@company_ai_router.put("/settings")
def update_company_ai_settings(
    payload: CompanyAISettingsUpdate,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Update company allowed AI providers and default models."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    # Validate against platform enabled providers
    if payload.allowed_providers is not None:
        enabled_plat = {p.provider_key for p in db.query(PlatformAIProvider).filter(PlatformAIProvider.is_enabled == True).all()}
        disallowed = [p for p in payload.allowed_providers if p not in enabled_plat]
        if disallowed:
            raise HTTPException(
                status_code=400,
                detail=f"Providers {disallowed} are disabled by platform policy.",
            )

    comp_setting = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company_id).first()
    if not comp_setting:
        comp_setting = CompanyAISetting(company_id=company_id)
        db.add(comp_setting)

    if payload.allowed_providers is not None:
        comp_setting.allowed_providers = payload.allowed_providers
    if payload.default_read_provider is not None:
        comp_setting.default_read_provider = payload.default_read_provider
    if payload.default_read_model is not None:
        comp_setting.default_read_model = payload.default_read_model
    if payload.default_generate_provider is not None:
        comp_setting.default_generate_provider = payload.default_generate_provider
    if payload.default_generate_model is not None:
        comp_setting.default_generate_model = payload.default_generate_model

    db.commit()
    db.refresh(comp_setting)

    audit.record(
        db=db,
        action=AI_CONFIG_UPDATE,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=company_id,
        object_type="company_ai_settings",
        object_id=company_id,
        metadata={"description": f"Company #{company_id} updated allowed AI providers to {comp_setting.allowed_providers}"},
    )
    return {"message": "Company AI settings updated successfully"}


@company_ai_router.post("/consent")
def grant_company_ai_consent(
    payload: ConsentRequest,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Grant explicit company consent for an external AI provider."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    # Verify provider exists and is enabled
    plat = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == payload.provider_key).first()
    if not plat or not plat.is_enabled:
        raise HTTPException(status_code=400, detail=f"AI provider '{payload.provider_key}' is not available.")

    consent = (
        db.query(CompanyAIConsent)
        .filter(
            CompanyAIConsent.company_id == company_id,
            CompanyAIConsent.provider_key == payload.provider_key,
        )
        .first()
    )
    version = payload.policy_version or payload.consented_terms_version or "1.0"
    if consent:
        consent.is_consented = True
        consent.consented_at = datetime.utcnow()
        consent.consented_by = auth_ctx.user_id
        consent.policy_version = version
    else:
        consent = CompanyAIConsent(
            company_id=company_id,
            provider_key=payload.provider_key,
            is_consented=True,
            consented_at=datetime.utcnow(),
            consented_by=auth_ctx.user_id,
            policy_version=version,
        )
        db.add(consent)

    db.commit()

    audit.record(
        db=db,
        action=AI_CONSENT_GRANT,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=company_id,
        object_type="company_ai_consent",
        object_id=consent.id,
        metadata={"description": f"Company #{company_id} granted explicit consent for AI provider '{payload.provider_key}'"},
    )
    return {"message": f"Consent granted for '{payload.provider_key}'.", "status": "consented"}


@company_ai_router.post("/consent/revoke")
def revoke_company_ai_consent(
    payload: RevokeConsentRequest,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Revoke company consent for an external AI provider."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    consent = (
        db.query(CompanyAIConsent)
        .filter(
            CompanyAIConsent.company_id == company_id,
            CompanyAIConsent.provider_key == payload.provider_key,
        )
        .first()
    )
    if not consent or not consent.is_consented:
        return {"message": f"Consent was not active for '{payload.provider_key}'.", "status": "revoked"}

    consent.is_consented = False
    db.commit()

    audit.record(
        db=db,
        action=AI_CONSENT_REVOKE,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=company_id,
        object_type="company_ai_consent",
        object_id=consent.id,
        metadata={"description": f"Company #{company_id} REVOKED consent for AI provider '{payload.provider_key}'"},
    )
    return {"message": f"Consent revoked for '{payload.provider_key}'.", "status": "revoked"}


@company_ai_router.get("/credentials", response_model=List[CredentialOut])
def list_company_credentials(
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """List company-scoped AI credentials with masked values."""
    auth_ctx.assert_active_company()
    creds = (
        db.query(AICredential)
        .filter(AICredential.scope_type == "company", AICredential.scope_id == auth_ctx.company_id)
        .all()
    )
    results = []
    for c in creds:
        try:
            plain = decrypt_api_key(c.encrypted_key)
            masked = mask_api_key(plain)
        except Exception:
            masked = "••••••••"
        results.append(CredentialOut(
            id=c.id,
            provider_key=c.provider_key,
            scope_type=c.scope_type,
            scope_id=c.scope_id,
            masked_key=masked,
            status=c.status,
            created_at=c.created_at,
        ))
    return results


@company_ai_router.post("/credentials", response_model=CredentialOut)
def create_company_credential(
    payload: CredentialCreate,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Save encrypted company-level AI credential (write-only)."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    enc_key = encrypt_api_key(payload.api_key.strip())
    masked = mask_api_key(payload.api_key.strip())
    existing = (
        db.query(AICredential)
        .filter(
            AICredential.scope_type == "company",
            AICredential.scope_id == company_id,
            AICredential.provider_key == payload.provider_key,
        )
        .first()
    )
    if existing:
        existing.encrypted_key = enc_key
        existing.masked_key = masked
        existing.status = "active"
        existing.updated_at = datetime.utcnow()
        cred = existing
    else:
        cred = AICredential(
            provider_key=payload.provider_key,
            scope_type="company",
            scope_id=company_id,
            encrypted_key=enc_key,
            masked_key=masked,
            status="active",
        )
        db.add(cred)

    db.commit()
    db.refresh(cred)

    audit.record(
        db=db,
        action=AI_CREDENTIAL_CREATE,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=company_id,
        object_type="ai_credential",
        object_id=cred.id,
        metadata={"description": f"Saved encrypted company credential for provider '{payload.provider_key}'"},
    )

    return CredentialOut(
        id=cred.id,
        provider_key=cred.provider_key,
        scope_type=cred.scope_type,
        scope_id=cred.scope_id,
        masked_key=mask_api_key(payload.api_key.strip()),
        status=cred.status,
        created_at=cred.created_at,
    )


@company_ai_router.delete("/credentials/{credential_id}")
def delete_company_credential(
    credential_id: int,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Delete a company credential."""
    auth_ctx.assert_active_company()
    cred = (
        db.query(AICredential)
        .filter(
            AICredential.id == credential_id,
            AICredential.scope_type == "company",
            AICredential.scope_id == auth_ctx.company_id,
        )
        .first()
    )
    if not cred:
        raise HTTPException(status_code=404, detail="Company credential not found.")
    db.delete(cred)
    db.commit()

    audit.record(
        db=db,
        action=AI_CREDENTIAL_DELETE,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=auth_ctx.company_id,
        object_type="ai_credential",
        object_id=credential_id,
        metadata={"description": f"Deleted company credential #{credential_id} for '{cred.provider_key}'"},
    )
    return {"message": "Credential deleted successfully"}


@company_ai_router.get("/usage")
def get_company_ai_usage(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    branch_id: Optional[int] = Query(None),
    provider: Optional[str] = Query(None),
    operation: Optional[str] = Query(None),
    auth_ctx: AuthContext = Depends(require_permission(AI_USAGE_VIEW)),
    db: Session = Depends(get_db),
):
    """Attempt-level AI processing logs and aggregated cost/token metrics."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    query = db.query(AIProcessingLog).filter(AIProcessingLog.company_id == company_id)

    if branch_id:
        query = query.filter(AIProcessingLog.branch_id == branch_id)
    if provider:
        query = query.filter(AIProcessingLog.provider == provider)
    if operation:
        query = query.filter(AIProcessingLog.operation == operation)

    total_count = query.count()

    # Aggregates
    agg = (
        db.query(
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("total_cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("total_tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("total_tokens_out"),
            func.coalesce(func.avg(AIProcessingLog.latency_ms), 0).label("avg_latency_ms"),
            func.count(AIProcessingLog.id).label("total_attempts"),
            func.sum(func.case((AIProcessingLog.success == True, 1), else_=0)).label("successful_attempts"),
            func.sum(func.case((AIProcessingLog.success == False, 1), else_=0)).label("failed_attempts"),
        )
        .filter(AIProcessingLog.company_id == company_id)
    )
    if branch_id:
        agg = agg.filter(AIProcessingLog.branch_id == branch_id)
    agg_res = agg.first()

    items = (
        query.order_by(desc(AIProcessingLog.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    log_items = []
    for row in items:
        log_items.append({
            "id": row.id,
            "company_id": row.company_id,
            "branch_id": row.branch_id,
            "document_id": row.document_id,
            "job_id": row.job_id,
            "operation": row.operation,
            "provider": row.provider,
            "model": row.model,
            "is_fallback": row.is_fallback,
            "attempt_number": row.attempt_number,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "cost_cents": row.cost_cents,
            "latency_ms": row.latency_ms,
            "success": row.success,
            "error_code": row.error_code,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {
        "items": log_items,
        "total_count": total_count,
        "aggregates": {
            "total_cost_cents": int(agg_res.total_cost_cents) if agg_res else 0,
            "total_tokens_in": int(agg_res.total_tokens_in) if agg_res else 0,
            "total_tokens_out": int(agg_res.total_tokens_out) if agg_res else 0,
            "avg_latency_ms": int(round(agg_res.avg_latency_ms)) if agg_res else 0,
            "total_attempts": int(agg_res.total_attempts) if agg_res else 0,
            "successful_attempts": int(agg_res.successful_attempts) if agg_res else 0,
            "failed_attempts": int(agg_res.failed_attempts) if agg_res else 0,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. BRANCH AI ENDPOINTS (Branch Admin & Company Admin)
# ─────────────────────────────────────────────────────────────────────────────

@branch_ai_router.get("/{branch_id}/ai/config")
def get_branch_ai_config(
    branch_id: int,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """Retrieve operation-specific AI configuration for a specific branch."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    # Verify branch belongs to company
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found.")

    configs = db.query(BranchAIConfig).filter(
        BranchAIConfig.company_id == company_id,
        BranchAIConfig.branch_id == branch_id,
    ).all()

    config_map = {c.operation: BranchAIConfigOut.from_orm(c) for c in configs}

    # Fetch company-level defaults
    comp_setting = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company_id).first()

    return {
        "branch_id": branch_id,
        "company_id": company_id,
        "configs": config_map,
        "company_defaults": {
            "read": {
                "provider": comp_setting.default_read_provider if comp_setting else "gemini",
                "model": comp_setting.default_read_model if comp_setting else "gemini-2.0-flash",
            },
            "generate": {
                "provider": comp_setting.default_generate_provider if comp_setting else "gemini",
                "model": comp_setting.default_generate_model if comp_setting else "gemini-2.0-flash",
            },
            "allowed_providers": comp_setting.allowed_providers if comp_setting and comp_setting.allowed_providers else ["gemini", "openai", "anthropic"],
        },
    }


@branch_ai_router.put("/{branch_id}/ai/config", response_model=BranchAIConfigOut)
def upsert_branch_ai_config(
    branch_id: int,
    payload: BranchAIConfigIn,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Upsert operation-specific AI configuration for a branch.
    Enforces that primary and fallback providers are enabled platform-wide and allowed by the company.
    """
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    # 1. Verify branch tenancy
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found.")

    # 2. Check company allowed providers
    comp_setting = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company_id).first()
    allowed_providers = comp_setting.allowed_providers if comp_setting and comp_setting.allowed_providers else ["gemini", "openai", "anthropic"]

    if payload.primary_provider not in allowed_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{payload.primary_provider}' is not permitted by Company policy.",
        )

    # 3. Check platform provider availability and model allow-list
    plat_primary = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == payload.primary_provider).first()
    if not plat_primary or not plat_primary.is_enabled:
        raise HTTPException(status_code=400, detail=f"AI provider '{payload.primary_provider}' is disabled platform-wide.")
    if plat_primary.model_allow_list and payload.primary_model not in plat_primary.model_allow_list:
        raise HTTPException(status_code=400, detail=f"Model '{payload.primary_model}' is not in platform allow-list for '{payload.primary_provider}'.")

    # 4. Check fallback provider if supplied
    if payload.fallback_provider:
        if payload.fallback_provider == payload.primary_provider:
            raise HTTPException(status_code=400, detail="Fallback provider must be different from primary provider.")
        if payload.fallback_provider not in allowed_providers:
            raise HTTPException(status_code=400, detail=f"Fallback provider '{payload.fallback_provider}' is not permitted by Company policy.")
        plat_fallback = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == payload.fallback_provider).first()
        if not plat_fallback or not plat_fallback.is_enabled:
            raise HTTPException(status_code=400, detail=f"Fallback provider '{payload.fallback_provider}' is disabled platform-wide.")
        if payload.fallback_model and plat_fallback.model_allow_list and payload.fallback_model not in plat_fallback.model_allow_list:
            raise HTTPException(status_code=400, detail=f"Model '{payload.fallback_model}' is not in platform allow-list for '{payload.fallback_provider}'.")

    # 5. Upsert BranchAIConfig
    branch_cfg = (
        db.query(BranchAIConfig)
        .filter(
            BranchAIConfig.company_id == company_id,
            BranchAIConfig.branch_id == branch_id,
            BranchAIConfig.operation == payload.operation,
        )
        .first()
    )
    if not branch_cfg:
        branch_cfg = BranchAIConfig(
            company_id=company_id,
            branch_id=branch_id,
            operation=payload.operation,
        )
        db.add(branch_cfg)

    branch_cfg.primary_provider = payload.primary_provider
    branch_cfg.primary_model = payload.primary_model
    branch_cfg.fallback_provider = payload.fallback_provider
    branch_cfg.fallback_model = payload.fallback_model
    branch_cfg.max_retries = payload.max_retries
    branch_cfg.timeout_seconds = payload.timeout_seconds

    db.commit()
    db.refresh(branch_cfg)

    audit.record(
        db=db,
        action=AI_CONFIG_UPDATE,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=company_id,
        object_type="branch_ai_config",
        object_id=branch_cfg.id,
        metadata={"description": f"Branch #{branch_id} configured operation '{payload.operation}': primary={payload.primary_provider}/{payload.primary_model}, fallback={payload.fallback_provider}/{payload.fallback_model}"},
    )

    return BranchAIConfigOut.from_orm(branch_cfg)


@branch_ai_router.post("/{branch_id}/ai/test-connection", response_model=ConnectionTestResponse)
def test_branch_ai_connection(
    branch_id: int,
    payload: ConnectionTestRequest,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """Test AI provider connection for a branch."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    # Verify branch belongs to company
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found.")

    success, msg, latency = AIExecutionService.test_provider_connection(
        db=db,
        company_id=company_id,
        branch_id=branch_id,
        provider_key=payload.provider_key,
        model=payload.model,
        api_key=payload.api_key,
        actor_user_id=auth_ctx.user_id,
    )
    return ConnectionTestResponse(success=success, message=msg, latency_ms=latency)
