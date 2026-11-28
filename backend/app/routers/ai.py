"""
Module 10 — Centralized AI Provider and Model Management APIs (Master Admin Controlled).

Architectural Invariant:
- Master Admin (platform owner) has exclusive authority over AI infrastructure, provider credentials,
  model catalogues, and company-specific AI model assignments.
- Company Admin cannot add/update API keys, activate/deactivate providers, or directly override models.
- Companies can submit requests for specific AI providers or models, which Master Admin approves or rejects.
- Every AI operation resolves the Master Admin-approved company model assignment on the backend.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, desc, case
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
    CompanyAIConsent, BranchAIConfig, AICredential, AIProcessingLog,
    AIModelCatalogue, CompanyAIModelAssignment, CompanyAIModelRequest,
    MasterAdmin, User
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
    AI_MODEL_CATALOGUE_UPDATE,
    AI_MODEL_ASSIGNMENT_UPDATE,
    AI_MODEL_REQUEST_CREATE,
    AI_MODEL_REQUEST_APPROVE,
    AI_MODEL_REQUEST_REJECT,
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


class PlatformProviderCreate(BaseModel):
    provider_key: str = Field(..., min_length=2, max_length=32)
    display_name: str = Field(..., min_length=2, max_length=64)
    is_enabled: bool = True
    model_allow_list: List[str] = Field(default_factory=list)
    supported_operations: List[str] = Field(default_factory=lambda: ["read", "generate"])


class PlatformProviderUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    model_allow_list: Optional[List[str]] = None
    display_name: Optional[str] = None
    supported_operations: Optional[List[str]] = None


class ModelCatalogueCreate(BaseModel):
    provider_key: str = Field(..., min_length=2, max_length=32)
    model_id: str = Field(..., min_length=2, max_length=64)
    display_name: str = Field(..., min_length=2, max_length=64)
    capabilities: List[str] = Field(default_factory=lambda: ["ocr", "extraction", "generation"])
    is_active: bool = True
    metadata_json: Optional[Dict[str, Any]] = None


class ModelCatalogueUpdate(BaseModel):
    display_name: Optional[str] = None
    capabilities: Optional[List[str]] = None
    is_active: Optional[bool] = None
    metadata_json: Optional[Dict[str, Any]] = None


class ModelCatalogueOut(BaseModel):
    id: int
    provider_key: str
    model_id: str
    display_name: str
    capabilities: List[str]
    is_active: bool
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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


class CompanyModelAssignmentItem(BaseModel):
    task_type: str = Field(..., min_length=2, max_length=32)  # 'ocr', 'extraction', 'generation'
    provider_key: str = Field(..., min_length=2, max_length=32)
    model_id: str = Field(..., min_length=2, max_length=64)
    is_enabled: bool = True


class CompanyModelAssignmentOut(BaseModel):
    id: int
    company_id: int
    task_type: str
    provider_key: str
    model_id: str
    is_enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompanyAssignmentsBulkUpdate(BaseModel):
    assignments: List[CompanyModelAssignmentItem]
    is_ai_enabled: Optional[bool] = None
    monthly_ai_budget_cents: Optional[int] = None
    monthly_ai_budget_dollars: Optional[float] = None


class CompanyAIModelRequestCreate(BaseModel):
    provider_key: str = Field(..., min_length=2, max_length=32)
    model_id: str = Field(..., min_length=2, max_length=64)
    task_type: str = Field(..., min_length=2, max_length=32)
    reason: str = Field(..., min_length=5)


class CompanyAIModelRequestOut(BaseModel):
    id: int
    company_id: int
    company_name: Optional[str] = None
    requested_by: Optional[int] = None
    requester_name: Optional[str] = None
    provider_key: str
    model_id: str
    task_type: str
    reason: str
    status: str
    decision_by: Optional[int] = None
    decision_reason: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RequestDecisionIn(BaseModel):
    reason: Optional[str] = None
    decision_notes: Optional[str] = None
    auto_assign: bool = True


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


class CompanyAIInfoOut(BaseModel):
    company_id: int
    is_ai_enabled: bool
    assignments: List[Dict[str, Any]]
    available_capabilities: List[str]
    budget: Dict[str, Any]
    available_catalogue_models: List[Dict[str, Any]]


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
# 1. PLATFORM AI ENDPOINTS (Master Admin Exclusively)
# ─────────────────────────────────────────────────────────────────────────────

@platform_ai_router.get("/providers", response_model=List[PlatformProviderOut])
def list_platform_providers(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """List all AI providers and model allow-lists available on the platform."""
    providers = db.query(PlatformAIProvider).order_by(PlatformAIProvider.id.asc()).all()
    return providers


@platform_ai_router.post("/providers", response_model=PlatformProviderOut)
def create_platform_provider(
    payload: PlatformProviderCreate,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Add a new AI provider to the platform."""
    existing = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == payload.provider_key.strip().lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Provider '{payload.provider_key}' already exists.")

    prov = PlatformAIProvider(
        provider_key=payload.provider_key.strip().lower(),
        display_name=payload.display_name.strip(),
        is_enabled=payload.is_enabled,
        model_allow_list=payload.model_allow_list,
        supported_operations=payload.supported_operations,
    )
    db.add(prov)
    db.commit()
    db.refresh(prov)

    audit.record(
        db=db,
        action=AI_CONFIG_UPDATE,
        actor_type="master_admin",
        actor_id=admin_ctx.admin_id if hasattr(admin_ctx, "admin_id") else getattr(admin_ctx, "user_id", None),
        object_type="ai_provider",
        object_id=prov.id,
        metadata={"description": f"Added AI provider '{prov.provider_key}' ({prov.display_name})"},
    )
    return prov


@platform_ai_router.put("/providers/{provider_key}", response_model=PlatformProviderOut)
def update_platform_provider(
    provider_key: str,
    payload: PlatformProviderUpdate,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Enable/disable an AI provider or update its platform configuration."""
    provider = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == provider_key).first()
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_key}' not found.")

    if payload.is_enabled is not None:
        provider.is_enabled = payload.is_enabled
    if payload.display_name is not None:
        provider.display_name = payload.display_name.strip()
    if payload.model_allow_list is not None:
        provider.model_allow_list = payload.model_allow_list
    if payload.supported_operations is not None:
        provider.supported_operations = payload.supported_operations

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


# ── AI Model Catalogue (Master Admin) ───────────────────────────────────────

@platform_ai_router.get("/models", response_model=List[ModelCatalogueOut])
def list_catalogue_models(
    provider_key: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """List all AI models registered in the platform catalogue."""
    q = db.query(AIModelCatalogue)
    if provider_key:
        q = q.filter(AIModelCatalogue.provider_key == provider_key)
    if is_active is not None:
        q = q.filter(AIModelCatalogue.is_active == is_active)
    return q.order_by(AIModelCatalogue.provider_key.asc(), AIModelCatalogue.id.asc()).all()


@platform_ai_router.post("/models", response_model=ModelCatalogueOut)
def create_catalogue_model(
    payload: ModelCatalogueCreate,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Register a new AI model in the platform catalogue."""
    provider = db.query(PlatformAIProvider).filter(PlatformAIProvider.provider_key == payload.provider_key.strip().lower()).first()
    if not provider:
        raise HTTPException(status_code=400, detail=f"Provider '{payload.provider_key}' does not exist.")

    existing = (
        db.query(AIModelCatalogue)
        .filter(
            AIModelCatalogue.provider_key == payload.provider_key.strip().lower(),
            AIModelCatalogue.model_id == payload.model_id.strip(),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Model '{payload.model_id}' is already registered for provider '{payload.provider_key}'.")

    model_entry = AIModelCatalogue(
        provider_key=payload.provider_key.strip().lower(),
        model_id=payload.model_id.strip(),
        display_name=payload.display_name.strip(),
        capabilities=payload.capabilities,
        is_active=payload.is_active,
        metadata_json=payload.metadata_json,
    )
    db.add(model_entry)

    # Sync to provider model_allow_list if not present
    if payload.model_id.strip() not in (provider.model_allow_list or []):
        new_allow_list = list(provider.model_allow_list or [])
        new_allow_list.append(payload.model_id.strip())
        provider.model_allow_list = new_allow_list

    db.commit()
    db.refresh(model_entry)

    audit.record(
        db=db,
        action=AI_MODEL_CATALOGUE_UPDATE,
        actor_type="master_admin",
        actor_id=admin_ctx.admin_id if hasattr(admin_ctx, "admin_id") else getattr(admin_ctx, "user_id", None),
        object_type="ai_model",
        object_id=model_entry.id,
        metadata={"description": f"Added model '{model_entry.model_id}' to provider '{model_entry.provider_key}'"},
    )
    return model_entry


@platform_ai_router.put("/models/{model_id_val}", response_model=ModelCatalogueOut)
def update_catalogue_model(
    model_id_val: int,
    payload: ModelCatalogueUpdate,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Update catalogue model display name, capabilities, or active availability."""
    model_entry = db.query(AIModelCatalogue).filter(AIModelCatalogue.id == model_id_val).first()
    if not model_entry:
        raise HTTPException(status_code=404, detail=f"Catalogue model #{model_id_val} not found.")

    if payload.display_name is not None:
        model_entry.display_name = payload.display_name.strip()
    if payload.capabilities is not None:
        model_entry.capabilities = payload.capabilities
    if payload.is_active is not None:
        model_entry.is_active = payload.is_active
    if payload.metadata_json is not None:
        model_entry.metadata_json = payload.metadata_json

    db.commit()
    db.refresh(model_entry)

    audit.record(
        db=db,
        action=AI_MODEL_CATALOGUE_UPDATE,
        actor_type="master_admin",
        actor_id=admin_ctx.admin_id if hasattr(admin_ctx, "admin_id") else getattr(admin_ctx, "user_id", None),
        object_type="ai_model",
        object_id=model_entry.id,
        metadata={"description": f"Updated model #{model_entry.id} ({model_entry.model_id}): active={model_entry.is_active}"},
    )
    return model_entry


@platform_ai_router.delete("/models/{model_id_val}")
def delete_catalogue_model(
    model_id_val: int,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Deactivate or remove a model from the catalogue."""
    model_entry = db.query(AIModelCatalogue).filter(AIModelCatalogue.id == model_id_val).first()
    if not model_entry:
        raise HTTPException(status_code=404, detail="Model not found.")

    db.delete(model_entry)
    db.commit()

    audit.record(
        db=db,
        action=AI_MODEL_CATALOGUE_UPDATE,
        actor_type="master_admin",
        actor_id=admin_ctx.admin_id if hasattr(admin_ctx, "admin_id") else getattr(admin_ctx, "user_id", None),
        object_type="ai_model",
        object_id=model_id_val,
        metadata={"description": f"Deleted model #{model_id_val} from catalogue"},
    )
    return {"message": "Model removed from catalogue"}


# ── Platform Credentials (Master Admin) ─────────────────────────────────────

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
    """Save or rotate encrypted platform-level AI credential (write-only)."""
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


# ── Company-Specific Model Assignments (Master Admin) ───────────────────────

@platform_ai_router.get("/company-assignments")
def list_all_company_assignments_summary(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """List summary of all companies and their configured AI model assignments."""
    companies = db.query(Company).order_by(Company.name.asc()).all()
    rate = get_usd_to_inr_rate(db)
    results = []

    for comp in companies:
        settings_rec = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == comp.id).first()
        assignments = (
            db.query(CompanyAIModelAssignment)
            .filter(CompanyAIModelAssignment.company_id == comp.id)
            .order_by(CompanyAIModelAssignment.task_type.asc())
            .all()
        )
        assignment_map = {
            a.task_type: {
                "provider_key": a.provider_key,
                "model_id": a.model_id,
                "is_enabled": a.is_enabled,
            }
            for a in assignments
        }
        assignment_list = [
            {
                "task_type": a.task_type,
                "provider_key": a.provider_key,
                "model_id": a.model_id,
                "is_enabled": a.is_enabled,
            }
            for a in assignments
        ]
        pending_requests_count = (
            db.query(func.count(CompanyAIModelRequest.id))
            .filter(CompanyAIModelRequest.company_id == comp.id, CompanyAIModelRequest.status == "pending")
            .scalar() or 0
        )
        budget_usd = round((comp.monthly_ai_budget_cents or 0) / 100.0, 2)
        spent_usd = round((comp.ai_budget_spent_cents or 0) / 100.0, 2)

        results.append({
            "company_id": comp.id,
            "company_name": comp.name,
            "company_status": comp.status,
            "is_ai_enabled": settings_rec.is_ai_enabled if settings_rec and hasattr(settings_rec, "is_ai_enabled") else True,
            "monthly_ai_budget_dollars": budget_usd,
            "assignments": assignment_map,
            "assignment_list": assignment_list,
            "pending_requests_count": pending_requests_count,
            "budget": {
                "monthly_ai_budget_cents": comp.monthly_ai_budget_cents or 2500,
                "monthly_ai_budget_usd": budget_usd,
                "monthly_ai_budget_inr": comp.monthly_ai_budget_inr or round(budget_usd * rate, 2),
                "ai_budget_spent_cents": comp.ai_budget_spent_cents or 0,
                "ai_budget_spent_usd": spent_usd,
                "ai_budget_spent_inr": comp.ai_budget_spent_inr or round(spent_usd * rate, 2),
                "percent_used": round((spent_usd / budget_usd * 100), 1) if budget_usd > 0 else 0,
            },
        })
    return results


@platform_ai_router.get("/companies/{company_id}/assignments")
def get_company_assignments_detail(
    company_id: int,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Retrieve detailed AI model assignments and configuration for a specific company."""
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found.")

    settings_rec = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == comp.id).first()
    assignments = (
        db.query(CompanyAIModelAssignment)
        .filter(CompanyAIModelAssignment.company_id == comp.id)
        .order_by(CompanyAIModelAssignment.task_type.asc())
        .all()
    )
    rate = get_usd_to_inr_rate(db)
    budget_usd = round((comp.monthly_ai_budget_cents or 0) / 100.0, 2)
    spent_usd = round((comp.ai_budget_spent_cents or 0) / 100.0, 2)

    return {
        "company_id": comp.id,
        "company_name": comp.name,
        "is_ai_enabled": settings_rec.is_ai_enabled if settings_rec and hasattr(settings_rec, "is_ai_enabled") else True,
        "monthly_ai_budget_dollars": budget_usd,
        "assignments": [CompanyModelAssignmentOut.from_orm(a) for a in assignments],
        "budget": {
            "monthly_ai_budget_cents": comp.monthly_ai_budget_cents or 2500,
            "monthly_ai_budget_usd": budget_usd,
            "monthly_ai_budget_inr": comp.monthly_ai_budget_inr or round(budget_usd * rate, 2),
            "ai_budget_spent_cents": comp.ai_budget_spent_cents or 0,
            "ai_budget_spent_usd": spent_usd,
            "ai_budget_spent_inr": comp.ai_budget_spent_inr or round(spent_usd * rate, 2),
            "percent_used": round((spent_usd / budget_usd * 100), 1) if budget_usd > 0 else 0,
        },
    }


@platform_ai_router.put("/companies/{company_id}/assignments")
def update_company_assignments(
    company_id: int,
    payload: CompanyAssignmentsBulkUpdate,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Configure company-specific AI model assignments, toggle AI access, and configure monthly budget."""
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found.")

    settings_rec = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == comp.id).first()
    if not settings_rec:
        settings_rec = CompanyAISetting(company_id=comp.id)
        db.add(settings_rec)

    if payload.is_ai_enabled is not None:
        settings_rec.is_ai_enabled = payload.is_ai_enabled

    cents = payload.monthly_ai_budget_cents
    if cents is None and payload.monthly_ai_budget_dollars is not None:
        cents = int(round(payload.monthly_ai_budget_dollars * 100))
    if cents is not None:
        rate = get_usd_to_inr_rate(db)
        comp.monthly_ai_budget_cents = cents
        comp.monthly_ai_budget_inr = round((cents / 100.0) * rate, 2)

    admin_id = getattr(admin_ctx, "admin_id", None) or getattr(admin_ctx, "user_id", None)

    for item in payload.assignments:
        task = item.task_type.strip().lower()
        existing = (
            db.query(CompanyAIModelAssignment)
            .filter(
                CompanyAIModelAssignment.company_id == company_id,
                CompanyAIModelAssignment.task_type == task,
            )
            .first()
        )
        if existing:
            existing.provider_key = item.provider_key.strip().lower()
            existing.model_id = item.model_id.strip()
            existing.is_enabled = item.is_enabled
            existing.updated_at = datetime.utcnow()
        else:
            new_assign = CompanyAIModelAssignment(
                company_id=company_id,
                task_type=task,
                provider_key=item.provider_key.strip().lower(),
                model_id=item.model_id.strip(),
                is_enabled=item.is_enabled,
                created_by=admin_id,
            )
            db.add(new_assign)

    db.commit()

    audit.record(
        db=db,
        action=AI_MODEL_ASSIGNMENT_UPDATE,
        actor_type="master_admin",
        actor_id=admin_id,
        company_id=company_id,
        object_type="ai_assignment",
        object_id=company_id,
        metadata={"description": f"Updated AI assignments for Company #{company_id} ({comp.name})"},
    )
    return {"message": f"AI model assignments updated successfully for {comp.name}."}


@platform_ai_router.delete("/companies/{company_id}/assignments/{task_type}")
def delete_company_task_assignment(
    company_id: int,
    task_type: str,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Remove a company-specific model assignment for a task."""
    assignment = (
        db.query(CompanyAIModelAssignment)
        .filter(
            CompanyAIModelAssignment.company_id == company_id,
            CompanyAIModelAssignment.task_type == task_type.strip().lower(),
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail=f"No assignment found for task '{task_type}'.")

    db.delete(assignment)
    db.commit()

    admin_id = getattr(admin_ctx, "admin_id", None) or getattr(admin_ctx, "user_id", None)
    audit.record(
        db=db,
        action=AI_MODEL_ASSIGNMENT_UPDATE,
        actor_type="master_admin",
        actor_id=admin_id,
        company_id=company_id,
        object_type="ai_assignment",
        object_id=company_id,
        metadata={"description": f"Removed AI assignment for task '{task_type}' for Company #{company_id}"},
    )
    return {"message": f"Assignment for task '{task_type}' removed."}


# ── AI Model Requests (Master Admin Review) ─────────────────────────────────

@platform_ai_router.get("/requests", response_model=List[CompanyAIModelRequestOut])
def list_company_model_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    company_id: Optional[int] = Query(None),
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """List company AI model requests with filtering by status and company."""
    q = db.query(CompanyAIModelRequest)
    if status_filter:
        q = q.filter(CompanyAIModelRequest.status == status_filter.strip().lower())
    if company_id:
        q = q.filter(CompanyAIModelRequest.company_id == company_id)

    requests_db = q.order_by(desc(CompanyAIModelRequest.created_at)).all()
    results = []
    for r in requests_db:
        comp_name = r.company.name if r.company else f"Company #{r.company_id}"
        req_name = r.requester.name if r.requester else "Unknown"
        results.append(CompanyAIModelRequestOut(
            id=r.id,
            company_id=r.company_id,
            company_name=comp_name,
            requested_by=r.requested_by,
            requester_name=req_name,
            provider_key=r.provider_key,
            model_id=r.model_id,
            task_type=r.task_type,
            reason=r.reason,
            status=r.status,
            decision_by=r.decision_by,
            decision_reason=r.decision_reason,
            decided_at=r.decided_at,
            created_at=r.created_at,
        ))
    return results


@platform_ai_router.post("/requests/{request_id}/approve")
def approve_company_model_request(
    request_id: int,
    payload: RequestDecisionIn,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Approve a company AI model request and configure the company assignment."""
    req_rec = db.query(CompanyAIModelRequest).filter(CompanyAIModelRequest.id == request_id).first()
    if not req_rec:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req_rec.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request #{request_id} is already '{req_rec.status}'.")

    admin_id = getattr(admin_ctx, "admin_id", None) or getattr(admin_ctx, "user_id", None)
    req_rec.status = "approved"
    req_rec.decision_by = admin_id
    req_rec.decision_reason = payload.reason or payload.decision_notes or "Approved by Master Admin."
    req_rec.decided_at = datetime.utcnow()

    # Automatically configure company assignment upon approval
    if payload.auto_assign:
        existing = (
            db.query(CompanyAIModelAssignment)
            .filter(
                CompanyAIModelAssignment.company_id == req_rec.company_id,
                CompanyAIModelAssignment.task_type == req_rec.task_type,
            )
            .first()
        )
        if existing:
            existing.provider_key = req_rec.provider_key
            existing.model_id = req_rec.model_id
            existing.is_enabled = True
            existing.updated_at = datetime.utcnow()
        else:
            new_assign = CompanyAIModelAssignment(
                company_id=req_rec.company_id,
                task_type=req_rec.task_type,
                provider_key=req_rec.provider_key,
                model_id=req_rec.model_id,
                is_enabled=True,
                created_by=admin_id,
            )
            db.add(new_assign)

    db.commit()

    audit.record(
        db=db,
        action=AI_MODEL_REQUEST_APPROVE,
        actor_type="master_admin",
        actor_id=admin_id,
        company_id=req_rec.company_id,
        object_type="ai_request",
        object_id=req_rec.id,
        metadata={"description": f"Approved AI request #{req_rec.id} for Company #{req_rec.company_id}: model {req_rec.model_id} for {req_rec.task_type}"},
    )
    return {
        "id": req_rec.id,
        "status": req_rec.status,
        "decision_notes": req_rec.decision_reason,
        "message": f"Request #{request_id} approved successfully.",
    }


@platform_ai_router.post("/requests/{request_id}/reject")
def reject_company_model_request(
    request_id: int,
    payload: RequestDecisionIn,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Reject a company AI model request with an explicit reason."""
    req_rec = db.query(CompanyAIModelRequest).filter(CompanyAIModelRequest.id == request_id).first()
    if not req_rec:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req_rec.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request #{request_id} is already '{req_rec.status}'.")

    admin_id = getattr(admin_ctx, "admin_id", None) or getattr(admin_ctx, "user_id", None)
    req_rec.status = "rejected"
    req_rec.decision_by = admin_id
    req_rec.decision_reason = payload.reason or payload.decision_notes or "Rejected by platform administrator."
    req_rec.decided_at = datetime.utcnow()

    db.commit()

    audit.record(
        db=db,
        action=AI_MODEL_REQUEST_REJECT,
        actor_type="master_admin",
        actor_id=admin_id,
        company_id=req_rec.company_id,
        object_type="ai_request",
        object_id=req_rec.id,
        metadata={"description": f"Rejected AI request #{req_rec.id} for Company #{req_rec.company_id}: {req_rec.decision_reason}"},
    )
    return {
        "id": req_rec.id,
        "status": req_rec.status,
        "decision_reason": req_rec.decision_reason,
        "message": f"Request #{request_id} rejected.",
    }


# ── AI Usage Overview (Master Admin) ────────────────────────────────────────

@platform_ai_router.get("/usage-overview")
def get_master_admin_usage_overview(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Platform-wide AI usage, cost, and budget compliance overview for Master Admin."""
    rate = get_usd_to_inr_rate(db)

    # Aggregates across all companies
    agg = (
        db.query(
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("total_cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("total_tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("total_tokens_out"),
            func.count(AIProcessingLog.id).label("total_attempts"),
            func.sum(case((AIProcessingLog.success == False, 1), else_=0)).label("failed_attempts"),
        )
        .first()
    )

    # Provider breakdown with success counting
    provider_breakdown = (
        db.query(
            AIProcessingLog.provider,
            func.count(AIProcessingLog.id).label("requests_count"),
            func.sum(case((AIProcessingLog.success == True, 1), else_=0)).label("successful_requests"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
        )
        .group_by(AIProcessingLog.provider)
        .all()
    )

    prov_dict = {
        row.provider: {
            "provider": row.provider,
            "requests_count": row.requests_count,
            "total_requests": row.requests_count,
            "successful_requests": int(row.successful_requests or 0),
            "cost_cents": int(row.cost_cents or 0),
            "cost_usd": round((row.cost_cents or 0) / 100.0, 4),
            "total_cost_usd": round((row.cost_cents or 0) / 100.0, 4),
            "cost_inr": round(((row.cost_cents or 0) / 100.0) * rate, 2),
        }
        for row in provider_breakdown
    }

    # Ensure all registered foundation providers are visible in breakdown
    plat_providers = db.query(PlatformAIProvider).all()
    for pp in plat_providers:
        if pp.provider_key not in prov_dict:
            prov_dict[pp.provider_key] = {
                "provider": pp.provider_key,
                "requests_count": 0,
                "total_requests": 0,
                "successful_requests": 0,
                "cost_cents": 0,
                "cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "cost_inr": 0.0,
            }

    providers_list = list(prov_dict.values())

    # Company breakdown
    company_breakdown = (
        db.query(
            Company.id,
            Company.name,
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("spent_cents"),
            func.count(AIProcessingLog.id).label("request_count"),
            Company.monthly_ai_budget_cents,
        )
        .outerjoin(AIProcessingLog, AIProcessingLog.company_id == Company.id)
        .group_by(Company.id, Company.name, Company.monthly_ai_budget_cents)
        .order_by(desc("spent_cents"))
        .all()
    )

    comp_list = [
        {
            "company_id": row.id,
            "company_name": row.name,
            "spent_cents": int(row.spent_cents or 0),
            "spent_usd": round((row.spent_cents or 0) / 100.0, 4),
            "current_spend_usd": round((row.spent_cents or 0) / 100.0, 4),
            "spent_inr": round(((row.spent_cents or 0) / 100.0) * rate, 2),
            "budget_cents": row.monthly_ai_budget_cents or 2500,
            "budget_usd": round((row.monthly_ai_budget_cents or 2500) / 100.0, 2),
            "monthly_budget_dollars": round((row.monthly_ai_budget_cents or 2500) / 100.0, 2),
            "request_count": row.request_count,
        }
        for row in company_breakdown
    ]

    total_cost_usd = round((agg.total_cost_cents or 0) / 100.0, 4)
    total_cost_inr = round(total_cost_usd * rate, 2)

    return {
        "platform_totals": {
            "total_cost_cents": int(agg.total_cost_cents or 0),
            "total_cost_usd": total_cost_usd,
            "total_cost_inr": total_cost_inr,
            "total_tokens_in": int(agg.total_tokens_in or 0),
            "total_tokens_out": int(agg.total_tokens_out or 0),
            "total_attempts": int(agg.total_attempts or 0),
            "failed_attempts": int(agg.failed_attempts or 0),
            "exchange_rate": rate,
        },
        "total_requests": int(agg.total_attempts or 0),
        "total_cost_usd": total_cost_usd,
        "total_cost_inr": total_cost_inr,
        "failed_requests": int(agg.failed_attempts or 0),
        "providers": providers_list,
        "provider_breakdown": providers_list,
        "companies": comp_list,
        "company_breakdown": comp_list,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. COMPANY AI ENDPOINTS (Company Admin Read-Only & Request Workflow)
# ─────────────────────────────────────────────────────────────────────────────

@company_ai_router.get("/info", response_model=CompanyAIInfoOut)
def get_company_ai_info(
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Read-only AI information page for Company Admin.
    Displays enabled status, Master Admin assigned models, budget, consumption, and available capabilities.
    Does NOT leak API credentials or sensitive infrastructure details.
    """
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found.")

    settings_rec = db.query(CompanyAISetting).filter(CompanyAISetting.company_id == company_id).first()
    is_enabled = settings_rec.is_ai_enabled if settings_rec and hasattr(settings_rec, "is_ai_enabled") else True

    # Get approved assignments
    assignments_db = (
        db.query(CompanyAIModelAssignment)
        .filter(CompanyAIModelAssignment.company_id == company_id)
        .order_by(CompanyAIModelAssignment.task_type.asc())
        .all()
    )

    # Map model metadata from catalogue
    catalogue_models = db.query(AIModelCatalogue).filter(AIModelCatalogue.is_active == True).all()
    cat_map = {(m.provider_key, m.model_id): m for m in catalogue_models}

    task_labels = {
        "ocr": "OCR & Document Text Extraction",
        "read": "OCR & Document Text Extraction",
        "extraction": "Structured Invoice Data Extraction",
        "generation": "Outbound Invoice Generation",
        "generate": "Outbound Invoice Generation",
    }

    assignment_list = []
    for a in assignments_db:
        cat_item = cat_map.get((a.provider_key, a.model_id))
        display_name = cat_item.display_name if cat_item else a.model_id
        assignment_list.append({
            "task_type": a.task_type,
            "task_label": task_labels.get(a.task_type, a.task_type.title()),
            "provider_key": a.provider_key,
            "provider_name": a.provider_key.upper(),
            "model_id": a.model_id,
            "model_display_name": display_name,
            "is_enabled": a.is_enabled,
        })

    rate = get_usd_to_inr_rate(db)
    budget_usd = round((comp.monthly_ai_budget_cents or 0) / 100.0, 2)
    spent_usd = round((comp.ai_budget_spent_cents or 0) / 100.0, 2)
    budget_inr = float(comp.monthly_ai_budget_inr or round(budget_usd * rate, 2))
    spent_inr = float(comp.ai_budget_spent_inr or round(spent_usd * rate, 2))

    available_models = [
        {
            "provider_key": m.provider_key,
            "model_id": m.model_id,
            "display_name": m.display_name,
            "capabilities": m.capabilities,
        }
        for m in catalogue_models
    ]

    return CompanyAIInfoOut(
        company_id=company_id,
        is_ai_enabled=is_enabled,
        assignments=assignment_list,
        available_capabilities=["ocr", "extraction", "generation"],
        budget={
            "monthly_ai_budget_cents": comp.monthly_ai_budget_cents or 2500,
            "monthly_ai_budget_usd": budget_usd,
            "monthly_ai_budget_inr": budget_inr,
            "ai_budget_spent_cents": comp.ai_budget_spent_cents or 0,
            "ai_budget_spent_usd": spent_usd,
            "ai_budget_spent_inr": spent_inr,
            "percent_used": round((spent_usd / budget_usd * 100), 1) if budget_usd > 0 else 0,
        },
        available_catalogue_models=available_models,
    )


@company_ai_router.get("/requests", response_model=List[CompanyAIModelRequestOut])
def list_company_requests(
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """List AI model requests submitted by the current company."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    requests_db = (
        db.query(CompanyAIModelRequest)
        .filter(CompanyAIModelRequest.company_id == company_id)
        .order_by(desc(CompanyAIModelRequest.created_at))
        .all()
    )
    results = []
    for r in requests_db:
        comp_name = r.company.name if r.company else f"Company #{r.company_id}"
        req_name = r.requester.name if r.requester else "Unknown"
        results.append(CompanyAIModelRequestOut(
            id=r.id,
            company_id=r.company_id,
            company_name=comp_name,
            requested_by=r.requested_by,
            requester_name=req_name,
            provider_key=r.provider_key,
            model_id=r.model_id,
            task_type=r.task_type,
            reason=r.reason,
            status=r.status,
            decision_by=r.decision_by,
            decision_reason=r.decision_reason,
            decided_at=r.decided_at,
            created_at=r.created_at,
        ))
    return results


@company_ai_router.post("/requests", response_model=CompanyAIModelRequestOut)
def submit_company_model_request(
    payload: CompanyAIModelRequestCreate,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """Submit an AI model request to Master Admin."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    # Validate provider and model exist in active catalogue
    model_cat = (
        db.query(AIModelCatalogue)
        .filter(
            AIModelCatalogue.provider_key == payload.provider_key.strip().lower(),
            AIModelCatalogue.model_id == payload.model_id.strip(),
            AIModelCatalogue.is_active == True,
        )
        .first()
    )
    if not model_cat:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{payload.model_id}' is not an active platform model for provider '{payload.provider_key}'.",
        )

    # Check for duplicate pending request for same task
    existing_pending = (
        db.query(CompanyAIModelRequest)
        .filter(
            CompanyAIModelRequest.company_id == company_id,
            CompanyAIModelRequest.task_type == payload.task_type.strip().lower(),
            CompanyAIModelRequest.status == "pending",
        )
        .first()
    )
    if existing_pending:
        raise HTTPException(
            status_code=400,
            detail=f"A pending request for task '{payload.task_type}' already exists (#Req-{existing_pending.id}). Please wait for administrator review.",
        )

    req_rec = CompanyAIModelRequest(
        company_id=company_id,
        requested_by=auth_ctx.user_id,
        provider_key=payload.provider_key.strip().lower(),
        model_id=payload.model_id.strip(),
        task_type=payload.task_type.strip().lower(),
        reason=payload.reason.strip(),
        status="pending",
    )
    db.add(req_rec)
    db.commit()
    db.refresh(req_rec)

    audit.record(
        db=db,
        action=AI_MODEL_REQUEST_CREATE,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=company_id,
        object_type="ai_request",
        object_id=req_rec.id,
        metadata={"description": f"Company #{company_id} submitted request for {payload.provider_key}/{payload.model_id} on '{payload.task_type}'"},
    )

    return CompanyAIModelRequestOut(
        id=req_rec.id,
        company_id=req_rec.company_id,
        company_name=auth_ctx.tenant_name if hasattr(auth_ctx, "tenant_name") else "",
        requested_by=req_rec.requested_by,
        requester_name=auth_ctx.user_name if hasattr(auth_ctx, "user_name") else "",
        provider_key=req_rec.provider_key,
        model_id=req_rec.model_id,
        task_type=req_rec.task_type,
        reason=req_rec.reason,
        status=req_rec.status,
        created_at=req_rec.created_at,
    )


@company_ai_router.post("/requests/{request_id}/cancel")
def cancel_company_model_request(
    request_id: int,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """Cancel a pending AI model request submitted by this company."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    req_rec = (
        db.query(CompanyAIModelRequest)
        .filter(
            CompanyAIModelRequest.id == request_id,
            CompanyAIModelRequest.company_id == company_id,
        )
        .first()
    )
    if not req_rec:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req_rec.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot cancel a request that is already '{req_rec.status}'.")

    req_rec.status = "cancelled"
    req_rec.decision_reason = "Cancelled by requesting company."
    req_rec.decided_at = datetime.utcnow()
    db.commit()

    return {"message": f"Request #{request_id} cancelled."}


# ── Restricted Company Endpoints (Enforce Master Admin Exclusivity) ─────────

@company_ai_router.get("/settings", response_model=CompanyAISettingsOut)
def get_company_ai_settings(
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """Get company AI configuration, consents, budgets, and available platform providers (read-only)."""
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
        default_read_model=comp_setting.default_read_model if comp_setting else "gemini-3.6-flash",
        default_generate_provider=comp_setting.default_generate_provider if comp_setting else "gemini",
        default_generate_model=comp_setting.default_generate_model if comp_setting else "gemini-3.6-flash",
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
    """
    Enforces that Company Admins CANNOT modify AI provider allow-lists or model selections.
    All model and provider selection is exclusively controlled by the platform Master Admin.
    """
    auth_ctx.assert_active_company()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="AI provider and model configuration is exclusively managed by the platform Master Admin. Please submit a model request via the Company Admin Portal.",
    )


@company_ai_router.get("/credentials")
def list_company_credentials(
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """Company Admins cannot view AI credentials."""
    auth_ctx.assert_active_company()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="AI credentials are exclusively managed by the platform Master Admin.",
    )


@company_ai_router.post("/credentials")
def create_company_credential(
    payload: CredentialCreate,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Company Admins cannot add or update AI credentials."""
    auth_ctx.assert_active_company()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="AI credentials are exclusively managed by the platform Master Admin.",
    )


@company_ai_router.delete("/credentials/{credential_id}")
def delete_company_credential(
    credential_id: int,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Company Admins cannot delete AI credentials."""
    auth_ctx.assert_active_company()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="AI credentials are exclusively managed by the platform Master Admin.",
    )


@company_ai_router.post("/consent")
def grant_company_consent(
    payload: ConsentRequest,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Grant explicit company-level data transfer consent for a specific AI provider."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    consent = (
        db.query(CompanyAIConsent)
        .filter(CompanyAIConsent.company_id == company_id, CompanyAIConsent.provider_key == payload.provider_key)
        .first()
    )
    if not consent:
        consent = CompanyAIConsent(
            company_id=company_id,
            provider_key=payload.provider_key,
        )
        db.add(consent)

    consent.is_consented = True
    consent.consented_by = auth_ctx.user_id
    consent.consented_at = datetime.utcnow()
    consent.policy_version = payload.policy_version or "1.0"
    consent.revoked_by = None
    consent.revoked_at = None

    db.commit()
    db.refresh(consent)

    audit.record(
        db=db,
        action=AI_CONSENT_GRANT,
        actor_type="company_admin",
        actor_id=auth_ctx.user_id,
        company_id=company_id,
        object_type="company_ai_consent",
        object_id=consent.id,
        metadata={"description": f"Company #{company_id} GRANTED consent for AI provider '{payload.provider_key}'"},
    )
    return {"message": f"Consent granted for '{payload.provider_key}'.", "status": "consented"}


@company_ai_router.post("/consent/revoke")
def revoke_company_consent(
    payload: RevokeConsentRequest,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """Revoke company-level data transfer consent for an AI provider immediately."""
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    consent = (
        db.query(CompanyAIConsent)
        .filter(CompanyAIConsent.company_id == company_id, CompanyAIConsent.provider_key == payload.provider_key)
        .first()
    )
    if not consent:
        raise HTTPException(status_code=404, detail=f"No consent record found for provider '{payload.provider_key}'.")

    consent.is_consented = False
    consent.revoked_by = auth_ctx.user_id
    consent.revoked_at = datetime.utcnow()

    db.commit()
    db.refresh(consent)

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

    # Fetch company-level defaults and assignments
    assignments = db.query(CompanyAIModelAssignment).filter(
        CompanyAIModelAssignment.company_id == company_id,
        CompanyAIModelAssignment.is_enabled == True,
    ).all()
    assign_map = {a.task_type: {"provider": a.provider_key, "model": a.model_id} for a in assignments}

    return {
        "branch_id": branch_id,
        "company_id": company_id,
        "configs": config_map,
        "company_assignments": assign_map,
    }


@branch_ai_router.put("/{branch_id}/ai/config", response_model=BranchAIConfigOut)
def upsert_branch_ai_config(
    branch_id: int,
    payload: BranchAIConfigIn,
    auth_ctx: AuthContext = Depends(require_permission(AI_SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Upsert operation-specific AI parameters (retries, timeouts) for a branch.
    Rejects unauthorized model overrides that conflict with Master Admin assignments.
    """
    auth_ctx.assert_active_company()
    company_id = auth_ctx.company_id

    # 1. Verify branch tenancy
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found.")

    # 2. Check that the provider and model match an active model in the catalogue
    model_cat = (
        db.query(AIModelCatalogue)
        .filter(
            AIModelCatalogue.provider_key == payload.primary_provider,
            AIModelCatalogue.model_id == payload.primary_model,
            AIModelCatalogue.is_active == True,
        )
        .first()
    )
    if not model_cat:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{payload.primary_model}' is not an active platform model for provider '{payload.primary_provider}'.",
        )

    # 3. Check Master Admin company assignment
    task = "ocr" if payload.operation == "read" else "generation"
    assignment = (
        db.query(CompanyAIModelAssignment)
        .filter(
            CompanyAIModelAssignment.company_id == company_id,
            CompanyAIModelAssignment.task_type.in_([task, payload.operation]),
            CompanyAIModelAssignment.is_enabled == True,
        )
        .first()
    )
    if assignment:
        if assignment.provider_key != payload.primary_provider or assignment.model_id != payload.primary_model:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized model override: Company #{company_id} has model '{assignment.model_id}' ({assignment.provider_key}) assigned by Master Admin for task '{task}'. Branch cannot override to '{payload.primary_model}'.",
            )

    # 4. Upsert BranchAIConfig
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
        metadata={"description": f"Branch #{branch_id} configured operation '{payload.operation}': primary={payload.primary_provider}/{payload.primary_model}"},
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
