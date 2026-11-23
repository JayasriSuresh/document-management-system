"""
Module 8 – Company Admin Router for Portal Operations.

Provides company-scoped self-service administrative APIs:
  1. Dashboard metrics (branches, users, documents, storage, AI budget, security status)
  2. Company profile viewing and updating
  3. Branch lifecycle (list, view, create, update, deactivate, activate) with quota and active-user safeguards
  4. User lifecycle (list, invite, update, multi-branch assignment, deactivate, activate)
  5. Last Active Company Admin protection (transactional enforcement)
  6. Force logout (session revocation & token_version increment)
  7. Admin-assisted MFA reset requests
  8. Company document archive with branch filtering
  9. Company audit logs with granular filters and pagination
"""

import hashlib
import logging
import math
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.audit import audit
from app.audit.events import (
    AUTH_INVITATION_CREATE as AUDIT_AUTH_INVITATION_CREATE,
    AUTH_INVITATION_REVOKE as AUDIT_AUTH_INVITATION_REVOKE,
    AUTH_MFA_RESET_BY_ADMIN,
    AUTH_SESSION_REVOKE,
    BRANCH_ASSIGNMENT_CHANGE,
    BRANCH_CREATE as AUDIT_BRANCH_CREATE,
    BRANCH_TOGGLE as AUDIT_BRANCH_TOGGLE,
    BRANCH_UPDATE as AUDIT_BRANCH_UPDATE,
    COMPANY_UPDATE as AUDIT_COMPANY_UPDATE,
    ROLE_ASSIGN,
    ROLE_REMOVE,
    USER_CREATE,
    USER_DEACTIVATE,
    USER_REACTIVATE,
    USER_UPDATE,
    ObjectType,
)
from app.auth.dependencies import require_permission, requires
from app.auth.permissions import (
    AUDIT_VIEW_COMPANY,
    BRANCH_CREATE,
    BRANCH_EDIT,
    BRANCH_VIEW,
    COMPANY_MANAGE,
    COMPANY_VIEW,
    DOCUMENT_VIEW_COMPANY,
    DOCUMENT_VIEW_OWN,
    MFA_MANAGE_COMPANY,
    USER_ASSIGN_ROLE,
    USER_DEACTIVATE as PERM_USER_DEACTIVATE,
    USER_INVITE,
    USER_VIEW,
)
from app.config import settings
from app.context import AuthContext, require_company, get_auth_context
from app.storage import get_storage_adapter
from app.database import get_db
from app.models import (
    AccountStatus,
    AIProcessingLog,
    AIUsageLedger,
    AuditLog,
    Branch,
    Company,
    CompanyOnboarding,
    CompanyStatus,
    Document,
    Invitation,
    User,
    UserRole,
    UserRoleAssignment,
)
from app.services.currency_service import get_usd_to_inr_rate, convert_usd_cents_to_inr
from app.repositories.documents import DocumentRepository
from app.schemas import (
    AuditLogPaginationResponse,
    BranchDetailOut,
    BranchUpdate,
    CompanyInvitationItem,
    CompanyProfileOut,
    CompanyProfileUpdate,
    CompanyUserInviteRequest,
    CompanyUserItem,
    CompanyUserUpdateRequest,
    CompanyUsersPaginationResponse,
    CreateBranchRequest,
    CreateBranchResponse,
    DocumentListItem,
    GenericMessageResponse,
    PrimaryAdminSummary,
)
from app.services.email_service import email_service
from app.services.invitation_service import hash_token
from app.services.mfa_service import MfaService
from app.services.session_service import session_service

logger = logging.getLogger("dms.routers.company")

router = APIRouter(prefix="/api/company", tags=["company"])


def _build_branch_detail(branch: Branch, db: Session, company_id: int) -> BranchDetailOut:
    """Helper to assemble rich BranchDetailOut response."""
    user_count = (
        db.query(func.count(User.id))
        .filter(User.branch_id == branch.id, User.company_id == company_id)
        .scalar()
        or 0
    )
    doc_count = (
        db.query(func.count(Document.id))
        .filter(Document.branch_id == branch.id, Document.company_id == company_id)
        .scalar()
        or 0
    )

    admin_user = (
        db.query(User)
        .filter(
            User.branch_id == branch.id,
            User.company_id == company_id,
            User.role == UserRole.ADMIN,
        )
        .first()
    )

    admin_summary = None
    if admin_user:
        admin_summary = PrimaryAdminSummary(
            id=admin_user.id,
            name=admin_user.name,
            email=admin_user.email,
            mobile=admin_user.mobile,
            status=admin_user.status.value,
            is_activated=bool(admin_user.status == AccountStatus.ACTIVE),
        )
    else:
        pending_inv = (
            db.query(Invitation)
            .filter(
                Invitation.branch_id == branch.id,
                Invitation.company_id == company_id,
                Invitation.invited_role == UserRole.ADMIN,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .order_by(Invitation.created_at.desc())
            .first()
        )
        if pending_inv:
            admin_summary = PrimaryAdminSummary(
                id=None,
                name="Pending Activation",
                email=pending_inv.email,
                mobile=None,
                status="pending_invitation",
                is_activated=False,
            )

    address_display = f"{branch.address_line1 or ''}{', ' + branch.address_line2 if branch.address_line2 else ''}".strip(", ") or None
    contact_person_val = (admin_user.name if admin_user else None) or branch.branch_email
    contact_email_val = branch.branch_email or (admin_user.email if admin_user else None)
    contact_phone_val = branch.branch_contact_number or (admin_user.mobile if admin_user else None)

    return BranchDetailOut(
        id=branch.id,
        company_id=branch.company_id,
        name=branch.name,
        code=branch.code,
        branch_type=branch.branch_type or "Branch",
        branch_email=branch.branch_email,
        branch_contact_number=branch.branch_contact_number,
        address_line1=branch.address_line1,
        address_line2=branch.address_line2,
        address=address_display,
        contact_person=contact_person_val,
        contact_email=contact_email_val,
        contact_phone=contact_phone_val,
        city=branch.city,
        district=branch.district,
        state=branch.state,
        pincode=branch.pincode,
        country=branch.country or "India",
        gst_registered=bool(branch.gst_registered),
        gstin=branch.gstin,
        gst_type=branch.gst_type,
        status=branch.status or "active",
        created_at=branch.created_at,
        user_count=user_count,
        active_user_count=user_count,
        total_user_count=user_count,
        document_count=doc_count,
        primary_admin=admin_summary,
    )


# ── 1. COMPANY DASHBOARD METRICS ─────────────────────────────────────────────

@router.get("/dashboard")
@requires(COMPANY_VIEW)
def get_company_dashboard(
    auth_ctx: AuthContext = Depends(require_permission(COMPANY_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Company-scoped metrics for Company Admin Dashboard.
    """
    auth_ctx.assert_active_company()
    # Lock company row to eliminate concurrent quota race conditions
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    total_branches = db.query(func.count(Branch.id)).filter(Branch.company_id == company.id).scalar() or 0
    active_branches = (
        db.query(func.count(Branch.id))
        .filter(Branch.company_id == company.id, or_(Branch.status == "active", Branch.status.is_(None)))
        .scalar()
        or 0
    )

    total_users = db.query(func.count(User.id)).filter(User.company_id == company.id).scalar() or 0
    active_users = (
        db.query(func.count(User.id))
        .filter(User.company_id == company.id, User.status == AccountStatus.ACTIVE)
        .scalar()
        or 0
    )

    total_docs = (
        db.query(func.count(Document.id))
        .filter(Document.company_id == company.id, Document.deleted_at.is_(None))
        .scalar()
        or 0
    )
    storage_used = (
        db.query(func.coalesce(func.sum(Document.file_size), 0))
        .filter(Document.company_id == company.id, Document.deleted_at.is_(None))
        .scalar()
        or 0
    )

    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rate = get_usd_to_inr_rate(db)

    # 1. Spend from AIUsageLedger
    ai_ledger_spend = (
        db.query(
            func.coalesce(func.sum(AIUsageLedger.cost_cents), 0).label("cents"),
            func.coalesce(func.sum(AIUsageLedger.cost_inr), 0.0).label("inr"),
        )
        .filter(
            AIUsageLedger.company_id == company.id,
            AIUsageLedger.created_at >= start_of_month,
            AIUsageLedger.status == "success",
        )
        .first()
    )
    ai_spent_cents_ledger = int(ai_ledger_spend.cents or 0)
    ai_spent_inr_ledger = float(ai_ledger_spend.inr or 0.0)

    # 2. Spend from AIProcessingLog
    ai_log_spend = (
        db.query(
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("inr"),
        )
        .filter(
            AIProcessingLog.company_id == company.id,
            AIProcessingLog.created_at >= start_of_month,
            AIProcessingLog.success == True,
        )
        .first()
    )
    ai_spent_cents_log = int(ai_log_spend.cents or 0)
    ai_spent_inr_log = float(ai_log_spend.inr or 0.0)

    # Reconciled USD spend and historical converted INR spend
    ai_spent_cents_int = max(ai_spent_cents_ledger, ai_spent_cents_log, company.ai_budget_spent_cents or 0)
    ai_spent_inr = max(ai_spent_inr_ledger, ai_spent_inr_log, float(company.ai_budget_spent_inr or 0.0))
    if ai_spent_inr == 0.0 and ai_spent_cents_int > 0:
        ai_spent_inr = convert_usd_cents_to_inr(ai_spent_cents_int, rate)

    ai_spent_usd = round(ai_spent_cents_int / 100.0, 2)
    ai_budget_cents = company.monthly_ai_budget_cents or 0
    monthly_ai_budget_usd = round(ai_budget_cents / 100.0, 2)

    monthly_ai_budget_inr = (
        float(company.monthly_ai_budget_inr)
        if company.monthly_ai_budget_inr is not None
        else round((ai_budget_cents / 100.0) * rate, 2)
    )

    ai_budget_usage_pct = (
        round((ai_spent_inr / monthly_ai_budget_inr * 100), 1)
        if monthly_ai_budget_inr > 0
        else (round((ai_spent_cents_int / ai_budget_cents * 100), 1) if ai_budget_cents > 0 else 0.0)
    )

    # 10 most recent company audit logs
    recent_logs = (
        db.query(AuditLog)
        .filter(AuditLog.company_id == company.id)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(10)
        .all()
    )
    recent_activity = [
        {
            "id": log.id,
            "action": log.action,
            "actor_type": log.actor_type,
            "actor_id": log.actor_id,
            "object_type": log.object_type,
            "object_id": log.object_id,
            "branch_id": log.branch_id,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
            "ip": log.ip,
        }
        for log in recent_logs
    ]

    branches_used = total_branches
    branches_remaining = max(0, (company.max_branches or 0) - total_branches)
    users_used = total_users
    users_remaining = max(0, (company.max_users or 0) - total_users)

    storage_limit_b = company.storage_limit_bytes or 0
    storage_used_b = int(storage_used)
    storage_usage_pct = round((storage_used_b / storage_limit_b * 100), 1) if storage_limit_b > 0 else 0.0

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "code": company.code,
            "display_name": company.display_name,
            "logo_url": company.logo_url,
            "status": company.status.value,
            "gstin": company.gstin,
            "pan": company.pan,
            "pan_number": company.pan,
            "address": company.address,
            "registered_address": company.address,
            "contact_person": company.contact_person,
            "contact_email": company.contact_email,
            "contact_phone": company.contact_phone,
            "website": company.website,
            "company_website": company.website,
            "mfa_required_for_all": bool(company.mfa_required_for_all),
        },
        "stats": {
            "total_branches": total_branches,
            "active_branches": active_branches,
            "total_users": total_users,
            "active_users": active_users,
            "total_documents": total_docs,
        },
        "quotas": {
            "max_branches": company.max_branches,
            "total_branches": total_branches,
            "active_branches": active_branches,
            "branches_used": branches_used,
            "branches_remaining": branches_remaining,
            "max_users": company.max_users,
            "total_users": total_users,
            "active_users": active_users,
            "users_used": users_used,
            "users_remaining": users_remaining,
            "storage_limit_bytes": storage_limit_b,
            "storage_used_bytes": storage_used_b,
            "storage_usage_pct": storage_usage_pct,
            # Dual Currency Metrics: USD for Provider Reconciliation, INR for Local Dashboard
            "monthly_ai_budget_cents": ai_budget_cents,
            "monthly_ai_budget_usd": monthly_ai_budget_usd,
            "ai_spent_cents": ai_spent_cents_int,
            "ai_spent_usd": ai_spent_usd,
            "ai_budget_used_cents": ai_spent_cents_int,
            "monthly_ai_budget_inr": monthly_ai_budget_inr,
            "ai_spent_inr": round(ai_spent_inr, 2),
            "exchange_rate": rate,
            "reporting_currency": company.reporting_currency or "INR",
            "ai_budget_usage_pct": ai_budget_usage_pct,
            "total_documents": total_docs,
        },
        "security": {
            "mfa_required_for_all": bool(company.mfa_required_for_all),
        },
        "recent_activity": recent_activity,
    }


# ── 2. COMPANY PROFILE MANAGEMENT ───────────────────────────────────────────

@router.get("/profile", response_model=CompanyProfileOut)
@requires(COMPANY_VIEW)
def get_company_profile(
    auth_ctx: AuthContext = Depends(require_permission(COMPANY_VIEW)),
    db: Session = Depends(get_db),
):
    """Retrieve full company profile and resource statistics."""
    auth_ctx.assert_active_company()
    # Lock company row to eliminate concurrent quota race conditions
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    branch_count = db.query(func.count(Branch.id)).filter(Branch.company_id == company.id).scalar() or 0
    user_count = (
        db.query(func.count(User.id))
        .filter(User.company_id == company.id, User.status == AccountStatus.ACTIVE)
        .scalar()
        or 0
    )
    doc_count = (
        db.query(func.count(Document.id))
        .filter(Document.company_id == company.id, Document.deleted_at.is_(None))
        .scalar()
        or 0
    )
    storage_used = (
        db.query(func.coalesce(func.sum(Document.file_size), 0))
        .filter(Document.company_id == company.id, Document.deleted_at.is_(None))
        .scalar()
        or 0
    )

    # Check if any profile fields can be synced from linked CompanyOnboarding or company.limits
    onboarding = (
        db.query(CompanyOnboarding)
        .filter(CompanyOnboarding.company_id == company.id)
        .first()
    )
    if not onboarding:
        onboarding = (
            db.query(CompanyOnboarding)
            .filter(CompanyOnboarding.legal_company_name == company.name)
            .order_by(CompanyOnboarding.id.desc())
            .first()
        )

    dirty = False
    if onboarding:
        if not company.display_name and onboarding.trade_name:
            company.display_name = onboarding.trade_name.strip() or None
            dirty = True
        if not company.pan:
            p_val = (onboarding.pan_number or "").strip().upper() or (company.limits or {}).get("pan")
            if p_val:
                company.pan = p_val
                dirty = True
        if not company.website and onboarding.company_website:
            company.website = onboarding.company_website.strip() or None
            dirty = True
        if not company.contact_person:
            cp_val = (onboarding.auth_contact_name or onboarding.contact_name or "").strip() or None
            if cp_val:
                company.contact_person = cp_val
                dirty = True
        if not company.contact_email:
            ce_val = (onboarding.auth_contact_email or onboarding.contact_email or "").strip().lower() or None
            if ce_val:
                company.contact_email = ce_val
                dirty = True
        if not company.contact_phone and onboarding.auth_contact_mobile:
            company.contact_phone = onboarding.auth_contact_mobile.strip() or None
            dirty = True
        if not company.address:
            addr_val = f"{onboarding.address_line1 or ''}, {onboarding.city or ''}, {onboarding.state or ''} - {onboarding.pincode or ''}".strip(", -")
            if addr_val:
                company.address = addr_val
                dirty = True
        if not company.gstin and onboarding.gstin:
            company.gstin = onboarding.gstin.strip().upper() or None
            dirty = True
    elif not company.pan and (company.limits or {}).get("pan"):
        company.pan = str(company.limits["pan"]).strip().upper()
        dirty = True

    if dirty:
        company.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(company)

    return CompanyProfileOut(
        id=company.id,
        name=company.name,
        code=company.code,
        display_name=company.display_name,
        trade_name=company.display_name,
        logo_url=company.logo_url,
        gstin=company.gstin,
        pan=company.pan,
        pan_number=company.pan,
        address=company.address,
        registered_address=company.address,
        contact_person=company.contact_person,
        contact_name=company.contact_person,
        auth_contact_name=company.contact_person,
        contact_email=company.contact_email,
        auth_contact_email=company.contact_email,
        contact_phone=company.contact_phone,
        auth_contact_mobile=company.contact_phone,
        website=company.website,
        company_website=company.website,
        status=company.status.value,
        mfa_required_for_all=bool(company.mfa_required_for_all),
        max_branches=company.max_branches,
        max_users=company.max_users,
        storage_limit_bytes=company.storage_limit_bytes,
        monthly_ai_budget_cents=company.monthly_ai_budget_cents,
        ai_budget_spent_cents=company.ai_budget_spent_cents,
        monthly_ai_budget_inr=company.monthly_ai_budget_inr,
        ai_budget_spent_inr=float(company.ai_budget_spent_inr or 0.0),
        reporting_currency=company.reporting_currency or "INR",
        branch_count=branch_count,
        user_count=user_count,
        document_count=doc_count,
        storage_used_bytes=int(storage_used),
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


@router.put("/profile", response_model=CompanyProfileOut)
@requires(COMPANY_MANAGE)
def update_company_profile(
    payload: CompanyProfileUpdate,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(COMPANY_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Update permitted company profile fields.
    Company ID and tenant code are strictly immutable.
    """
    auth_ctx.assert_active_company()
    # Lock company row to eliminate concurrent quota race conditions
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    changes = {}
    name_val = payload.name if payload.name is not None else payload.legal_company_name
    if name_val is not None and name_val.strip():
        company.name = name_val.strip()
        changes["name"] = company.name

    display_name_val = payload.display_name if payload.display_name is not None else payload.trade_name
    if display_name_val is not None:
        company.display_name = display_name_val.strip() or None
        changes["display_name"] = company.display_name

    if payload.logo_url is not None:
        company.logo_url = payload.logo_url.strip() or None
        changes["logo_url"] = company.logo_url

    contact_person_val = (
        payload.contact_person if payload.contact_person is not None
        else (payload.auth_contact_name if payload.auth_contact_name is not None else payload.contact_name)
    )
    if contact_person_val is not None:
        company.contact_person = contact_person_val.strip() or None
        changes["contact_person"] = company.contact_person

    contact_email_val = payload.contact_email if payload.contact_email is not None else payload.auth_contact_email
    if contact_email_val is not None:
        company.contact_email = contact_email_val.strip().lower() or None
        changes["contact_email"] = company.contact_email

    contact_phone_val = payload.contact_phone if payload.contact_phone is not None else payload.auth_contact_mobile
    if contact_phone_val is not None:
        company.contact_phone = contact_phone_val.strip() or None
        changes["contact_phone"] = company.contact_phone

    website_val = payload.website if payload.website is not None else payload.company_website
    if website_val is not None:
        company.website = website_val.strip() or None
        changes["website"] = company.website

    address_val = payload.address if payload.address is not None else payload.registered_address
    if address_val is not None:
        company.address = address_val.strip() or None
        changes["address"] = company.address

    if payload.gstin is not None:
        gstin_val = payload.gstin.strip().upper() or None
        if gstin_val and len(gstin_val) != 15:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GSTIN must be 15 alphanumeric characters.")
        company.gstin = gstin_val
        changes["gstin"] = company.gstin

    pan_val = payload.pan if payload.pan is not None else payload.pan_number
    if pan_val is not None:
        pan_clean = pan_val.strip().upper() or None
        if pan_clean and len(pan_clean) != 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PAN must be 10 characters.")
        company.pan = pan_clean
        changes["pan"] = company.pan

    company.updated_at = datetime.utcnow()

    audit.record_event(
        db=db,
        action=AUDIT_COMPANY_UPDATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.COMPANY,
        object_id=company.id,
        metadata={"changes": changes},
    )
    db.commit()
    db.refresh(company)

    return get_company_profile(auth_ctx=auth_ctx, db=db)


@router.post("/logo")
@requires(COMPANY_MANAGE)
async def upload_company_logo(
    file: UploadFile = File(...),
    request: Request = None,
    auth_ctx: AuthContext = Depends(require_permission(COMPANY_MANAGE)),
    db: Session = Depends(get_db),
):
    """Upload and set company logo."""
    auth_ctx.assert_active_company()
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    allowed_types = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image format. Allowed formats: PNG, JPG, JPEG, WEBP, SVG.",
        )

    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logo image size exceeds 2 MB limit.",
        )

    ext = allowed_types[content_type]
    storage_key = f"company_logos/{company.id}_logo{ext}"
    storage = get_storage_adapter()
    storage.save(storage_key, contents)

    logo_url = f"/api/company/{company.id}/logo?v={int(datetime.utcnow().timestamp())}"
    company.logo_url = logo_url
    company.updated_at = datetime.utcnow()

    if request:
        audit.record_event(
            db=db,
            action=AUDIT_COMPANY_UPDATE,
            request=request,
            auth_context=auth_ctx,
            object_type=ObjectType.COMPANY,
            object_id=company.id,
            metadata={"changes": {"logo_url": logo_url}},
        )

    db.commit()
    db.refresh(company)

    return {"logo_url": logo_url, "message": "Company logo uploaded successfully."}


@router.delete("/logo")
@requires(COMPANY_MANAGE)
def delete_company_logo(
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(COMPANY_MANAGE)),
    db: Session = Depends(get_db),
):
    """Remove company logo."""
    auth_ctx.assert_active_company()
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    storage = get_storage_adapter()
    for ext in [".png", ".jpg", ".webp", ".svg"]:
        k = f"company_logos/{company.id}_logo{ext}"
        if storage.exists(k):
            try:
                storage.delete(k)
            except Exception:
                pass

    company.logo_url = None
    company.updated_at = datetime.utcnow()

    audit.record_event(
        db=db,
        action=AUDIT_COMPANY_UPDATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.COMPANY,
        object_id=company.id,
        metadata={"changes": {"logo_url": None}},
    )

    db.commit()
    db.refresh(company)
    return {"message": "Company logo removed successfully.", "logo_url": None}


@router.get("/logo")
def get_my_company_logo(
    auth_ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Serve authenticated user's company logo."""
    return get_company_logo_by_id(company_id=auth_ctx.company_id, db=db)


@router.get("/{company_id}/logo")
def get_company_logo_by_id(
    company_id: int,
    db: Session = Depends(get_db),
):
    """Serve company logo for rendering in UI headers and sidebars."""
    storage = get_storage_adapter()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    for ext, mime in mime_map.items():
        k = f"company_logos/{company_id}_logo{ext}"
        if storage.exists(k):
            stream = storage.open_stream(k)
            return StreamingResponse(
                stream,
                media_type=mime,
                headers={"Cache-Control": "public, max-age=86400"},
            )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company logo not found.")


# ── 3. BRANCH MANAGEMENT ─────────────────────────────────────────────────────

@router.get("/branches", response_model=List[BranchDetailOut])
@requires(BRANCH_VIEW)
def list_company_branches(
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_VIEW)),
    db: Session = Depends(get_db),
):
    """List all branches belonging to the authenticated company."""
    auth_ctx.assert_active_company()
    branches = (
        db.query(Branch)
        .filter(Branch.company_id == auth_ctx.company_id)
        .order_by(Branch.created_at.asc())
        .all()
    )
    return [_build_branch_detail(b, db, auth_ctx.company_id) for b in branches]


@router.get("/branches/{branch_id}", response_model=BranchDetailOut)
@requires(BRANCH_VIEW)
def get_branch_details(
    branch_id: int,
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_VIEW)),
    db: Session = Depends(get_db),
):
    """Fetch details of a single branch belonging to the authenticated company."""
    auth_ctx.assert_active_company()
    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
        .first()
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found in your company.",
        )
    return _build_branch_detail(branch, db, auth_ctx.company_id)


@router.post("/branches", response_model=CreateBranchResponse)
@requires(BRANCH_CREATE)
def create_branch(
    payload: CreateBranchRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_CREATE)),
    db: Session = Depends(get_db),
):
    """
    Company Admin provisions a new branch under their company.
    Enforces quota against company.max_branches.
    """
    auth_ctx.assert_active_company()
    branch_name = payload.branch_name.strip()
    if not branch_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch Name is required.")

    branch_code = payload.branch_code.strip().upper()
    if not branch_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch Code is required.")

    # Validate unique branch code within the company
    existing_branch = (
        db.query(Branch)
        .filter(Branch.company_id == auth_ctx.company_id, Branch.code == branch_code)
        .first()
    )
    if existing_branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Branch code '{branch_code}' already exists in your company. Please choose a unique branch code.",
        )

    # Quota check with pessimistic row-lock to eliminate concurrency races
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if company:
        current_branch_count = db.query(Branch).filter(Branch.company_id == auth_ctx.company_id).count()
        if current_branch_count >= company.max_branches:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Company branch limit reached: maximum {company.max_branches} branches allowed.",
            )

    gst_registered = bool(payload.gst_registered)
    gstin = payload.gstin.strip().upper() if (gst_registered and payload.gstin) else None
    gst_type = payload.gst_type.strip() if (gst_registered and payload.gst_type) else None

    if gst_registered and not gstin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GSTIN is required when branch is marked as GST registered.",
        )

    admin_name = payload.admin_name.strip()
    admin_email = payload.admin_email.strip().lower()
    admin_mobile = payload.admin_mobile.strip()

    if not admin_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Primary Admin Name is required.")
    if not admin_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Primary Admin Email is required.")
    if not admin_mobile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Primary Admin Mobile Number is required.")

    existing_user = db.query(User).filter(User.email == admin_email).first()
    if existing_user and existing_user.status == AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A user with email '{admin_email}' is already registered and active in the system.",
        )

    new_branch = Branch(
        company_id=auth_ctx.company_id,
        name=branch_name,
        code=branch_code,
        branch_type=payload.branch_type.strip() if payload.branch_type else "Branch",
        branch_email=payload.branch_email.strip().lower() if payload.branch_email else None,
        branch_contact_number=payload.branch_contact_number.strip(),
        address_line1=payload.address_line1.strip(),
        address_line2=payload.address_line2.strip() if payload.address_line2 else None,
        city=payload.city.strip(),
        district=payload.district.strip(),
        state=payload.state.strip(),
        pincode=payload.pincode.strip(),
        country=payload.country.strip() if payload.country else "India",
        gst_registered=gst_registered,
        gstin=gstin,
        gst_type=gst_type,
        status="active",
    )
    db.add(new_branch)
    db.flush()

    if not existing_user:
        admin_user = User(
            company_id=auth_ctx.company_id,
            branch_id=new_branch.id,
            name=admin_name,
            email=admin_email,
            mobile=admin_mobile,
            password_hash="!pending_account_activation",
            role=UserRole.ADMIN,
            status=AccountStatus.INACTIVE,
            token_version=1,
            must_change_password=False,
            failed_attempts=0,
        )
        db.add(admin_user)
        db.flush()
    else:
        existing_user.company_id = auth_ctx.company_id
        existing_user.branch_id = new_branch.id
        existing_user.name = admin_name
        existing_user.mobile = admin_mobile
        existing_user.role = UserRole.ADMIN
        existing_user.status = AccountStatus.INACTIVE
        admin_user = existing_user

    # Add role assignment for new branch
    db.add(UserRoleAssignment(
        user_id=admin_user.id,
        role="ADMIN",
        scope_type="branch",
        scope_id=new_branch.id,
        created_by=auth_ctx.user_id,
    ))

    # Revoke prior invitations
    db.query(Invitation).filter(
        Invitation.email == admin_email,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    ).update({"revoked_at": datetime.utcnow()}, synchronize_session=False)

    raw_token = secrets.token_hex(32)
    token_hash = hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)

    invitation = Invitation(
        email=admin_email,
        company_id=auth_ctx.company_id,
        branch_id=new_branch.id,
        invited_role=UserRole.ADMIN,
        token_hash=token_hash,
        invited_by=auth_ctx.user_id,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    db.add(invitation)
    db.flush()

    audit.record_event(
        db=db,
        action=AUDIT_BRANCH_CREATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.BRANCH,
        object_id=new_branch.id,
        metadata={
            "branch_name": new_branch.name,
            "branch_code": new_branch.code,
            "city": new_branch.city,
            "state": new_branch.state,
        },
    )
    audit.record_event(
        db=db,
        action=AUDIT_AUTH_INVITATION_CREATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.INVITATION,
        object_id=invitation.id,
        metadata={
            "invited_role": "ADMIN",
            "branch_id": invitation.branch_id,
        },
    )
    db.commit()
    db.refresh(new_branch)

    try:
        email_service.send_branch_admin_activation_email(
            to_email=admin_email,
            admin_name=admin_name,
            company_name=auth_ctx.company_name,
            branch_name=new_branch.name,
            branch_code=new_branch.code,
            raw_token=raw_token,
        )
    except Exception as exc:
        logger.warning("Failed to deliver branch activation email: %s", exc)

    activation_url = f"{settings.FRONTEND_URL.rstrip('/')}/accept-invite?token={raw_token}"
    detail = _build_branch_detail(new_branch, db, auth_ctx.company_id)
    return CreateBranchResponse(
        message=f"Branch '{new_branch.name}' ({new_branch.code}) created successfully!",
        branch=detail,
        activation_url=activation_url,
    )


@router.put("/branches/{branch_id}", response_model=BranchDetailOut)
@requires(BRANCH_EDIT)
def update_branch(
    branch_id: int,
    payload: BranchUpdate,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_EDIT)),
    db: Session = Depends(get_db),
):
    """Update details of a branch belonging to the company."""
    auth_ctx.assert_active_company()
    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
        .first()
    )
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

    changes = {}
    if payload.name is not None:
        name_val = payload.name.strip()
        if not name_val:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot be empty.")
        branch.name = name_val
        changes["name"] = name_val
    if payload.branch_type is not None:
        branch.branch_type = payload.branch_type.strip()
        changes["branch_type"] = branch.branch_type
    email_val = payload.branch_email if payload.branch_email is not None else payload.contact_email
    if email_val is not None:
        branch.branch_email = email_val.strip().lower() or None
        changes["branch_email"] = branch.branch_email
    phone_val = payload.branch_contact_number if payload.branch_contact_number is not None else payload.contact_phone
    if phone_val is not None:
        branch.branch_contact_number = phone_val.strip() or None
        changes["branch_contact_number"] = branch.branch_contact_number
    addr_val = payload.address_line1 if payload.address_line1 is not None else payload.address
    if addr_val is not None:
        branch.address_line1 = addr_val.strip()
        changes["address_line1"] = branch.address_line1
    if payload.address_line2 is not None:
        branch.address_line2 = payload.address_line2.strip() or None
        changes["address_line2"] = branch.address_line2
    if payload.city is not None:
        branch.city = payload.city.strip()
        changes["city"] = branch.city
    if payload.district is not None:
        branch.district = payload.district.strip()
        changes["district"] = branch.district
    if payload.state is not None:
        branch.state = payload.state.strip()
        changes["state"] = branch.state
    if payload.pincode is not None:
        branch.pincode = payload.pincode.strip()
        changes["pincode"] = branch.pincode
    if payload.country is not None:
        branch.country = payload.country.strip() or "India"
        changes["country"] = branch.country
    if payload.gst_registered is not None:
        branch.gst_registered = bool(payload.gst_registered)
        changes["gst_registered"] = branch.gst_registered
    if payload.gstin is not None:
        branch.gstin = payload.gstin.strip().upper() or None
        changes["gstin"] = branch.gstin
    if payload.gst_type is not None:
        branch.gst_type = payload.gst_type.strip() or None
        changes["gst_type"] = branch.gst_type

    branch.updated_at = datetime.utcnow()

    audit.record_event(
        db=db,
        action=AUDIT_BRANCH_UPDATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.BRANCH,
        object_id=branch.id,
        metadata={"changes": changes},
    )
    db.commit()
    db.refresh(branch)

    return _build_branch_detail(branch, db, auth_ctx.company_id)


@router.post("/branches/{branch_id}/deactivate")
@requires(BRANCH_EDIT)
def deactivate_branch(
    branch_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_EDIT)),
    db: Session = Depends(get_db),
):
    """
    Deactivate a branch.
    Enforces the active-user protection rule: Cannot deactivate a branch that has active users.
    Preserves all historical documents and logs.
    """
    auth_ctx.assert_active_company()
    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
        .first()
    )
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

    if (branch.status or "active").lower() == "inactive":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch is already inactive.")

    # ── Protection Check: Active Users (Primary + Multi-Branch Assignments) ───
    active_primary_users = (
        db.query(func.count(User.id))
        .filter(
            User.branch_id == branch.id,
            User.company_id == auth_ctx.company_id,
            User.status == AccountStatus.ACTIVE,
        )
        .scalar()
        or 0
    )
    active_secondary_users = (
        db.query(func.count(UserRoleAssignment.id))
        .join(User, User.id == UserRoleAssignment.user_id)
        .filter(
            UserRoleAssignment.scope_type == "branch",
            UserRoleAssignment.scope_id == branch.id,
            User.status == AccountStatus.ACTIVE,
            User.company_id == auth_ctx.company_id,
        )
        .scalar()
        or 0
    )
    total_active = active_primary_users + active_secondary_users
    if total_active > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot deactivate branch '{branch.name}'. "
                f"There are {total_active} active user assignment(s) ({active_primary_users} primary, {active_secondary_users} multi-branch) currently assigned to this branch. "
                "Please reassign or deactivate all active users in this branch first."
            ),
        )

    # Invalidate pending invitations for this branch
    db.query(Invitation).filter(
        Invitation.branch_id == branch.id,
        Invitation.company_id == auth_ctx.company_id,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    ).update({"revoked_at": datetime.utcnow()}, synchronize_session=False)

    branch.status = "inactive"
    branch.updated_at = datetime.utcnow()

    audit.record_event(
        db=db,
        action=AUDIT_BRANCH_TOGGLE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.BRANCH,
        object_id=branch.id,
        metadata={"branch_name": branch.name, "status": "inactive"},
    )
    db.commit()

    return {"message": f"Branch '{branch.name}' has been deactivated.", "status": "inactive"}


@router.post("/branches/{branch_id}/activate")
@requires(BRANCH_EDIT)
def activate_branch(
    branch_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_EDIT)),
    db: Session = Depends(get_db),
):
    """Reactivate an inactive branch."""
    auth_ctx.assert_active_company()
    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
        .first()
    )
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

    branch.status = "active"
    branch.updated_at = datetime.utcnow()

    audit.record_event(
        db=db,
        action=AUDIT_BRANCH_TOGGLE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.BRANCH,
        object_id=branch.id,
        metadata={"branch_name": branch.name, "status": "active"},
    )
    db.commit()

    return {"message": f"Branch '{branch.name}' has been reactivated.", "status": "active"}


@router.post("/branches/{branch_id}/toggle-status")
@requires(BRANCH_EDIT)
def toggle_branch_status(
    branch_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_EDIT)),
    db: Session = Depends(get_db),
):
    """Legacy toggle branch endpoint with safety checks."""
    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
        .first()
    )
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

    if (branch.status or "active").lower() == "active":
        return deactivate_branch(branch_id=branch_id, request=request, auth_ctx=auth_ctx, db=db)
    else:
        return activate_branch(branch_id=branch_id, request=request, auth_ctx=auth_ctx, db=db)


# ── 4. USER MANAGEMENT ───────────────────────────────────────────────────────

@router.get("/users", response_model=CompanyUsersPaginationResponse)
@requires(USER_VIEW)
def list_company_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    role: Optional[str] = Query(default=None),
    branch_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    auth_ctx: AuthContext = Depends(require_permission(USER_VIEW)),
    db: Session = Depends(get_db),
):
    """
    List users belonging to the Company Admin's company with search, filtering, and pagination.
    """
    auth_ctx.assert_active_company()
    query = db.query(User).filter(User.company_id == auth_ctx.company_id)

    if role:
        query = query.filter(User.role == role.upper())

    if status:
        query = query.filter(User.status == status.lower())

    if branch_id:
        # Check primary branch or assigned via UserRoleAssignment
        assigned_user_ids = (
            db.query(UserRoleAssignment.user_id)
            .filter(UserRoleAssignment.scope_type == "branch", UserRoleAssignment.scope_id == branch_id)
            .subquery()
        )
        query = query.filter(or_(User.branch_id == branch_id, User.id.in_(assigned_user_ids)))

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.name.ilike(s),
                User.email.ilike(s),
                User.mobile.ilike(s),
            )
        )

    total_count = query.count()
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

    users = (
        query.order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Prefetch branches and assignments
    company_branches = {b.id: b for b in db.query(Branch).filter(Branch.company_id == auth_ctx.company_id).all()}

    items = []
    for u in users:
        # Resolve multi-branch assignments
        assignments = (
            db.query(UserRoleAssignment)
            .filter(UserRoleAssignment.user_id == u.id)
            .all()
        )
        assigned_branches = []
        for a in assignments:
            if a.scope_type == "branch" and a.scope_id in company_branches:
                br = company_branches[a.scope_id]
                assigned_branches.append({
                    "branch_id": br.id,
                    "branch_name": br.name,
                    "branch_code": br.code,
                    "role": a.role,
                })
            elif a.scope_type == "company":
                assigned_branches.append({
                    "branch_id": None,
                    "branch_name": "All Branches (Company-Wide)",
                    "branch_code": "ALL",
                    "role": a.role,
                })

        # Check MFA enrollment
        mfa_enabled = MfaService.is_mfa_enabled(db, "user", u.id)
        primary_br = company_branches.get(u.branch_id)

        items.append(
            CompanyUserItem(
                id=u.id,
                name=u.name,
                email=u.email,
                mobile=u.mobile,
                role=u.role.value if hasattr(u.role, "value") else str(u.role),
                status=u.status.value if hasattr(u.status, "value") else str(u.status),
                branch_id=u.branch_id,
                branch_name=primary_br.name if primary_br else "Unknown",
                primary_branch_id=u.branch_id,
                primary_branch_name=primary_br.name if primary_br else "Unknown",
                assigned_branches=assigned_branches,
                mfa_enabled=mfa_enabled,
                token_version=u.token_version or 1,
                last_login_at=None,
                created_at=u.created_at,
            )
        )

    return CompanyUsersPaginationResponse(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/users/invite", response_model=GenericMessageResponse)
@requires(USER_INVITE)
def invite_company_user(
    payload: CompanyUserInviteRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_INVITE)),
    db: Session = Depends(get_db),
):
    """
    Invite a new user to the company.
    Reuses Module 3 Invitation Service and enforces Module 7 user quota.
    Supports multi-branch assignments for eligible roles (ADMIN).
    Prevents privilege escalation (cannot invite Master Admin).
    """
    auth_ctx.assert_active_company()
    # Lock company row to eliminate concurrent quota race conditions
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    # 1. Privilege & Role Escalation Check
    raw_role = payload.role.strip().upper()
    if raw_role in ("MASTER_ADMIN", "ROOT") or "MASTER" in raw_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilege escalation prohibited: Company Admin cannot assign platform Master Admin roles.",
        )

    valid_roles = {"GLOBAL_ADMIN": UserRole.GLOBAL_ADMIN, "ADMIN": UserRole.ADMIN, "STAFF": UserRole.STAFF}
    if raw_role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{payload.role}'. Must be one of: {list(valid_roles.keys())}",
        )
    target_role = valid_roles[raw_role]

    # 2. Module 7 Quota Enforcement
    active_count = db.query(func.count(User.id)).filter(User.company_id == company.id, User.status == AccountStatus.ACTIVE).scalar() or 0
    pending_inv = (
        db.query(func.count(Invitation.id))
        .filter(
            Invitation.company_id == company.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .scalar()
        or 0
    )
    if (active_count + pending_inv) >= company.max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Company user limit reached: maximum {company.max_users} users allowed.",
        )

    # 3. Branch Validation
    effective_branch_id = payload.branch_id if payload.branch_id is not None else payload.primary_branch_id
    if effective_branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary branch is required.",
        )
    primary_branch = (
        db.query(Branch)
        .filter(Branch.id == effective_branch_id, Branch.company_id == company.id)
        .first()
    )
    if not primary_branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary branch does not belong to your company.",
        )
    if (primary_branch.status or "active").lower() == "inactive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Primary branch '{primary_branch.name}' is deactivated. Cannot assign users to an inactive branch.",
        )

    # Multi-branch assignment validation
    extra_branch_ids = payload.additional_branch_ids or []
    if extra_branch_ids:
        if target_role == UserRole.STAFF:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploader and Staff roles are restricted to a single branch.",
            )
        for b_id in extra_branch_ids:
            br = db.query(Branch).filter(Branch.id == b_id, Branch.company_id == company.id).first()
            if not br:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Additional branch #{b_id} does not belong to your company.",
                )
            if (br.status or "active").lower() == "inactive":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Additional branch '{br.name}' is deactivated.",
                )

    email = payload.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user and existing_user.status == AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{email}' is already registered and active in the system.",
        )

    # 4. Provision User record (Inactive until activation)
    if not existing_user:
        new_user = User(
            company_id=company.id,
            branch_id=primary_branch.id,
            name=payload.name.strip(),
            email=email,
            mobile=payload.mobile.strip() if payload.mobile else None,
            password_hash="!pending_account_activation",
            role=target_role,
            status=AccountStatus.INACTIVE,
            token_version=1,
            must_change_password=False,
            failed_attempts=0,
        )
        db.add(new_user)
        db.flush()
    else:
        existing_user.company_id = company.id
        existing_user.branch_id = primary_branch.id
        existing_user.name = payload.name.strip()
        existing_user.mobile = payload.mobile.strip() if payload.mobile else None
        existing_user.role = target_role
        existing_user.status = AccountStatus.INACTIVE
        new_user = existing_user

    # Provision UserRoleAssignment
    all_assigned_branch_ids = [primary_branch.id] + [b for b in extra_branch_ids if b != primary_branch.id]
    if target_role == UserRole.GLOBAL_ADMIN:
        db.add(UserRoleAssignment(
            user_id=new_user.id,
            role="GLOBAL_ADMIN",
            scope_type="company",
            scope_id=company.id,
            created_by=auth_ctx.user_id,
        ))
    else:
        for b_id in all_assigned_branch_ids:
            db.add(UserRoleAssignment(
                user_id=new_user.id,
                role=raw_role,
                scope_type="branch",
                scope_id=b_id,
                created_by=auth_ctx.user_id,
            ))

    # 5. Revoke previous invitations & issue fresh secure token
    db.query(Invitation).filter(
        Invitation.email == email,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    ).update({"revoked_at": datetime.utcnow()}, synchronize_session=False)

    raw_token = secrets.token_hex(32)
    token_hash = hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)

    invitation = Invitation(
        email=email,
        company_id=company.id,
        branch_id=primary_branch.id,
        invited_role=target_role,
        token_hash=token_hash,
        invited_by=auth_ctx.user_id,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    db.add(invitation)
    db.flush()

    audit.record_event(
        db=db,
        action=USER_CREATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=new_user.id,
        metadata={"email": email, "role": raw_role, "primary_branch_id": primary_branch.id},
    )
    audit.record_event(
        db=db,
        action=AUDIT_AUTH_INVITATION_CREATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.INVITATION,
        object_id=invitation.id,
        metadata={"email": email, "role": raw_role, "branch_id": primary_branch.id},
    )
    db.commit()

    try:
        email_service.send_invitation_email(
            to_email=email,
            company_name=company.name,
            branch_name=primary_branch.name,
            role=raw_role,
            raw_token=raw_token,
        )
    except Exception as exc:
        logger.warning("Failed to deliver invitation email: %s", exc)

    return GenericMessageResponse(
        message=f"Invitation successfully dispatched to '{email}' for role '{raw_role}'."
    )


@router.get("/invitations", response_model=List[CompanyInvitationItem])
@requires(USER_VIEW)
def list_company_invitations(
    auth_ctx: AuthContext = Depends(require_permission(USER_VIEW)),
    db: Session = Depends(get_db),
):
    """List pending and historical invitations for the company."""
    auth_ctx.assert_active_company()
    invs = (
        db.query(Invitation)
        .filter(Invitation.company_id == auth_ctx.company_id)
        .order_by(Invitation.created_at.desc())
        .limit(100)
        .all()
    )

    company_branches = {b.id: b for b in db.query(Branch).filter(Branch.company_id == auth_ctx.company_id).all()}
    inviters = {u.id: u.name for u in db.query(User).filter(User.company_id == auth_ctx.company_id).all()}
    active_user_emails = {
        u.email.lower(): u
        for u in db.query(User)
        .filter(User.company_id == auth_ctx.company_id, User.status == AccountStatus.ACTIVE)
        .all()
    }

    items = []
    now = datetime.utcnow()
    dirty = False
    for inv in invs:
        # If the user is already active in the company, auto-mark invitation as accepted
        if not inv.accepted_at and not inv.revoked_at and inv.email.lower() in active_user_emails:
            active_u = active_user_emails[inv.email.lower()]
            inv.accepted_at = active_u.created_at or now
            dirty = True

        is_accepted = bool(inv.accepted_at)
        is_revoked = bool(inv.revoked_at)
        is_expired = inv.expires_at < now
        is_valid = (not is_accepted) and (not is_revoked) and (not is_expired)

        if is_revoked:
            status_str = "revoked"
        elif is_accepted:
            status_str = "accepted"
        elif is_expired:
            status_str = "expired"
        else:
            status_str = "pending"

        br = company_branches.get(inv.branch_id)
        role_str = inv.invited_role.value if hasattr(inv.invited_role, "value") else str(inv.invited_role)

        items.append(
            CompanyInvitationItem(
                id=inv.id,
                email=inv.email,
                branch_id=inv.branch_id,
                branch_name=br.name if br else "Unknown",
                branch_code=br.code if br else None,
                invited_role=role_str,
                role=role_str,
                invited_by_name=inviters.get(inv.invited_by),
                expires_at=inv.expires_at,
                accepted_at=inv.accepted_at,
                revoked_at=inv.revoked_at,
                status=status_str,
                accepted=is_accepted,
                revoked=is_revoked,
                is_valid=is_valid,
                created_at=inv.created_at,
            )
        )
    if dirty:
        db.commit()
    return items


@router.post("/invitations/{invitation_id}/resend", response_model=GenericMessageResponse)
@requires(USER_INVITE)
def resend_company_invitation(
    invitation_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_INVITE)),
    db: Session = Depends(get_db),
):
    """Resend invitation with a fresh 72h token."""
    auth_ctx.assert_active_company()
    inv = (
        db.query(Invitation)
        .filter(Invitation.id == invitation_id, Invitation.company_id == auth_ctx.company_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

    if inv.accepted_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has already been accepted.")

    inv.revoked_at = datetime.utcnow()

    raw_token = secrets.token_hex(32)
    token_hash = hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)

    new_inv = Invitation(
        email=inv.email,
        company_id=inv.company_id,
        branch_id=inv.branch_id,
        invited_role=inv.invited_role,
        token_hash=token_hash,
        invited_by=auth_ctx.user_id,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    db.add(new_inv)
    db.commit()

    branch = db.query(Branch).filter(Branch.id == inv.branch_id).first()
    branch_name = branch.name if branch else "Main"
    role_str = inv.invited_role.value if hasattr(inv.invited_role, "value") else str(inv.invited_role)

    try:
        email_service.send_invitation_email(
            to_email=inv.email,
            company_name=auth_ctx.company_name,
            branch_name=branch_name,
            role=role_str,
            raw_token=raw_token,
        )
    except Exception as exc:
        logger.warning("Failed to resend invitation email: %s", exc)

    return GenericMessageResponse(message=f"Invitation re-sent successfully to '{inv.email}'.")


@router.post("/invitations/{invitation_id}/revoke", response_model=GenericMessageResponse)
@requires(USER_INVITE)
def revoke_company_invitation(
    invitation_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_INVITE)),
    db: Session = Depends(get_db),
):
    """Revoke a pending invitation."""
    auth_ctx.assert_active_company()
    inv = (
        db.query(Invitation)
        .filter(Invitation.id == invitation_id, Invitation.company_id == auth_ctx.company_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

    if inv.accepted_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot revoke an already accepted invitation.")

    inv.revoked_at = datetime.utcnow()

    audit.record_event(
        db=db,
        action=AUDIT_AUTH_INVITATION_REVOKE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.INVITATION,
        object_id=inv.id,
        metadata={"email": inv.email},
    )
    db.commit()

    return GenericMessageResponse(message=f"Invitation for '{inv.email}' has been revoked.")


@router.put("/users/{user_id}", response_model=GenericMessageResponse)
@requires(USER_ASSIGN_ROLE)
def update_company_user(
    user_id: int,
    payload: CompanyUserUpdateRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_ASSIGN_ROLE)),
    db: Session = Depends(get_db),
):
    """
    Update permitted user details, role assignment, and multi-branch scopes.
    Enforces Last Active Company Admin protection and privilege escalation prevention.
    """
    auth_ctx.assert_active_company()
    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in your company.")

    was_mfa_mandatory = MfaService.is_mfa_mandatory_for_user(db, target_user)

    # 1. Privilege Escalation Check
    if payload.role:
        raw_role = payload.role.strip().upper()
        if raw_role in ("MASTER_ADMIN", "ROOT") or "MASTER" in raw_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Privilege escalation prohibited: Cannot assign platform Master Admin.",
            )
        valid_roles = {"GLOBAL_ADMIN": UserRole.GLOBAL_ADMIN, "ADMIN": UserRole.ADMIN, "STAFF": UserRole.STAFF}
        if raw_role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {list(valid_roles.keys())}",
            )
        new_role = valid_roles[raw_role]

        # ── 2. LAST ACTIVE COMPANY ADMIN PROTECTION ────────────────────────────
        # If removing GLOBAL_ADMIN role from an active administrator, verify another active GLOBAL_ADMIN exists
        if target_user.role == UserRole.GLOBAL_ADMIN and new_role != UserRole.GLOBAL_ADMIN and target_user.status == AccountStatus.ACTIVE:
            # Acquire pessimistic lock on Company row to serialize concurrent demotions
            db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
            other_admins = (
                db.query(User.id)
                .filter(
                    User.company_id == auth_ctx.company_id,
                    User.role == UserRole.GLOBAL_ADMIN,
                    User.status == AccountStatus.ACTIVE,
                    User.id != target_user.id,
                )
                .all()
            )
            if not other_admins:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change role of the last active Company Administrator. Promote another administrator first.",
                )
        target_user.role = new_role

    if payload.name is not None:
        name_val = payload.name.strip()
        if name_val:
            target_user.name = name_val
    if payload.mobile is not None:
        target_user.mobile = payload.mobile.strip() or None

    # Branch updates
    effective_branch_id = payload.branch_id if payload.branch_id is not None else payload.primary_branch_id
    if effective_branch_id is not None:
        br = db.query(Branch).filter(Branch.id == effective_branch_id, Branch.company_id == auth_ctx.company_id).first()
        if not br:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch does not belong to your company.")
        if (br.status or "active").lower() == "inactive":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Branch '{br.name}' is inactive.")
        target_user.branch_id = br.id

    # Multi-branch assignment update
    if payload.additional_branch_ids is not None or payload.role is not None:
        extra_ids = payload.additional_branch_ids or []
        if extra_ids and target_user.role == UserRole.STAFF:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Staff and Uploader roles can only be assigned to a single branch.")

        # Re-provision UserRoleAssignment records
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == target_user.id).delete(synchronize_session=False)

        if target_user.role == UserRole.GLOBAL_ADMIN:
            db.add(UserRoleAssignment(
                user_id=target_user.id,
                role="GLOBAL_ADMIN",
                scope_type="company",
                scope_id=auth_ctx.company_id,
                created_by=auth_ctx.user_id,
            ))
        else:
            all_b_ids = [target_user.branch_id] + [b for b in extra_ids if b != target_user.branch_id]
            for b_id in all_b_ids:
                br = db.query(Branch).filter(Branch.id == b_id, Branch.company_id == auth_ctx.company_id).first()
                if br:
                    db.add(UserRoleAssignment(
                        user_id=target_user.id,
                        role=target_user.role.value if hasattr(target_user.role, "value") else str(target_user.role),
                        scope_type="branch",
                        scope_id=b_id,
                        created_by=auth_ctx.user_id,
                    ))

    # Invalidate active sessions immediately on role or branch scope modifications
    is_mfa_mandatory_now = MfaService.is_mfa_mandatory_for_user(db, target_user)
    if payload.role is not None or payload.branch_id is not None or payload.additional_branch_ids is not None:
        revocation_reason = (
            "mfa_policy_mandated_by_assignment_change"
            if (not was_mfa_mandatory and is_mfa_mandatory_now)
            else "role_or_scope_updated_by_admin"
        )
        session_service.revoke_all_sessions(
            db=db,
            identity_type="user",
            identity_id=target_user.id,
            reason=revocation_reason,
        )

    audit.record_event(
        db=db,
        action=USER_UPDATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"role": str(target_user.role), "branch_id": target_user.branch_id},
    )
    db.commit()

    return GenericMessageResponse(message=f"User '{target_user.email}' updated successfully.")


@router.post("/users/{user_id}/deactivate", response_model=GenericMessageResponse)
@requires(PERM_USER_DEACTIVATE)
def deactivate_company_user(
    user_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(PERM_USER_DEACTIVATE)),
    db: Session = Depends(get_db),
):
    """
    Deactivate a user account.
    Enforces the critical Last Active Company Admin protection rule.
    Immediately revokes all active sessions and increments token_version.
    """
    auth_ctx.assert_active_company()
    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in your company.")

    if target_user.status == AccountStatus.INACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already inactive.")

    # ── LAST ACTIVE COMPANY ADMIN PROTECTION ─────────────────────────────────
    if target_user.role == UserRole.GLOBAL_ADMIN:
        # Acquire pessimistic lock on Company row to serialize concurrent deactivations
        db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
        other_admins = (
            db.query(User.id)
            .filter(
                User.company_id == auth_ctx.company_id,
                User.role == UserRole.GLOBAL_ADMIN,
                User.status == AccountStatus.ACTIVE,
                User.id != target_user.id,
            )
            .all()
        )
        if not other_admins:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active Company Administrator for your company. Assign another Company Administrator before deactivating this account.",
            )

    target_user.status = AccountStatus.INACTIVE

    # Immediately invalidate all sessions and increment token_version
    session_service.revoke_all_sessions(db, identity_type="user", identity_id=target_user.id, reason="deactivated_by_admin")

    audit.record_event(
        db=db,
        action=USER_DEACTIVATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"email": target_user.email},
    )
    db.commit()

    return GenericMessageResponse(message=f"User '{target_user.email}' has been deactivated and logged out.")


@router.post("/users/{user_id}/activate", response_model=GenericMessageResponse)
@requires(PERM_USER_DEACTIVATE)
def activate_company_user(
    user_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(PERM_USER_DEACTIVATE)),
    db: Session = Depends(get_db),
):
    """
    Reactivate an inactive user account.
    Enforces Module 7 company user quota.
    """
    auth_ctx.assert_active_company()
    # Lock company row to eliminate concurrent quota race conditions
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in your company.")

    if target_user.status == AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already active.")

    # Quota check
    active_count = db.query(func.count(User.id)).filter(User.company_id == company.id, User.status == AccountStatus.ACTIVE).scalar() or 0
    if active_count >= company.max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Company user limit reached: maximum {company.max_users} users allowed. Cannot reactivate user.",
        )

    target_user.status = AccountStatus.ACTIVE

    audit.record_event(
        db=db,
        action=USER_REACTIVATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"email": target_user.email},
    )
    db.commit()

    return GenericMessageResponse(message=f"User '{target_user.email}' has been reactivated.")


# ── 5. FORCE LOGOUT & MFA RESET ──────────────────────────────────────────────

@router.post("/users/{user_id}/force-logout", response_model=GenericMessageResponse)
@requires(USER_ASSIGN_ROLE)
def force_logout_user(
    user_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_ASSIGN_ROLE)),
    db: Session = Depends(get_db),
):
    """
    Force logout a user across all active sessions.
    Revokes refresh tokens and increments token_version to reject existing access tokens.
    """
    auth_ctx.assert_active_company()
    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in your company.")

    revoked_count = session_service.revoke_all_sessions(
        db, identity_type="user", identity_id=target_user.id, reason="force_logout_by_company_admin"
    )

    audit.record_event(
        db=db,
        action=AUTH_SESSION_REVOKE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"action": "force_logout", "sessions_revoked": revoked_count, "email": target_user.email},
    )
    db.commit()

    return GenericMessageResponse(
        message=f"Successfully forced logout for '{target_user.email}'. All active sessions have been invalidated."
    )


@router.post("/users/{user_id}/mfa-reset-request", response_model=GenericMessageResponse)
@requires(MFA_MANAGE_COMPANY)
def request_user_mfa_reset(
    user_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(MFA_MANAGE_COMPANY)),
    db: Session = Depends(get_db),
):
    """
    Initiate an admin-assisted MFA reset for a company user.
    Invalidates current secret, recovery codes, and locks without exposing secrets.
    The user must complete fresh re-enrollment on next sign in.
    """
    auth_ctx.assert_active_company()
    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in your company.")

    MfaService.reset_mfa_by_admin(db, "user", target_user.id)

    audit.record_event(
        db=db,
        action=AUTH_MFA_RESET_BY_ADMIN,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"email": target_user.email},
    )
    db.commit()

    return GenericMessageResponse(
        message=f"MFA configuration reset successfully for '{target_user.email}'. User will be prompted to re-enroll upon login."
    )


# ── 6. COMPANY DOCUMENT ARCHIVE ──────────────────────────────────────────────

@router.get("/documents", response_model=List[DocumentListItem])
@requires(DOCUMENT_VIEW_COMPANY)
def list_company_archive(
    search: str = Query(default="", description="Search in OCR text or filename"),
    branch_id: Optional[int] = Query(default=None, description="Filter by branch ID"),
    auth_ctx: AuthContext = Depends(require_permission(DOCUMENT_VIEW_COMPANY)),
    db: Session = Depends(get_db),
):
    """
    Company-wide document archive for Company Admins across all branches.
    Strictly scoped to the Company Admin's own company.
    """
    auth_ctx.assert_active_company()
    repo = DocumentRepository(db, auth_ctx)
    docs = repo.list_documents(search=search, branch_id=branch_id)

    return [
        DocumentListItem(
            id=doc.id,
            original_filename=doc.original_filename,
            mime_type=doc.mime_type,
            file_size=doc.file_size,
            ocr_status=doc.ocr_status,
            created_at=doc.created_at,
            uploaded_by=doc.uploaded_by,
            uploader_name=doc.uploader.name if doc.uploader else "Unknown",
            company_id=doc.company_id,
            branch_id=doc.branch_id,
            branch_name=doc.branch.name if doc.branch else "",
            tenant_id=doc.branch_id,
        )
        for doc in docs
    ]


# ── 7. COMPANY AUDIT LOGS ────────────────────────────────────────────────────

@router.get("/audit-logs", response_model=AuditLogPaginationResponse)
@requires(AUDIT_VIEW_COMPANY)
def get_company_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    action: Optional[str] = Query(default=None),
    actor_type: Optional[str] = Query(default=None),
    actor_id: Optional[int] = Query(default=None),
    object_type: Optional[str] = Query(default=None),
    object_id: Optional[str] = Query(default=None),
    branch_id: Optional[int] = Query(default=None),
    auth_ctx: AuthContext = Depends(require_permission(AUDIT_VIEW_COMPANY)),
    db: Session = Depends(get_db),
):
    """
    Retrieve company-wide audit logs strictly scoped to the authenticated company.
    """
    auth_ctx.assert_active_company()
    query = db.query(AuditLog).filter(AuditLog.company_id == auth_ctx.company_id)

    if branch_id is not None:
        query = query.filter(AuditLog.branch_id == branch_id)

    if start_date:
        query = query.filter(AuditLog.occurred_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.occurred_at <= end_date)

    if action:
        query = query.filter(AuditLog.action == action)
    if actor_type:
        query = query.filter(AuditLog.actor_type == actor_type)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if object_type:
        query = query.filter(AuditLog.object_type == object_type)
    if object_id is not None:
        query = query.filter(AuditLog.object_id == str(object_id))

    total = query.count()
    pages = math.ceil(total / page_size) if total > 0 else 1

    records = (
        query.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    from app.schemas import AuditLogOut
    return AuditLogPaginationResponse(
        items=[
            AuditLogOut(
                id=log.id,
                action=log.action,
                actor_type=log.actor_type,
                actor_id=log.actor_id,
                company_id=log.company_id,
                branch_id=log.branch_id,
                object_type=log.object_type,
                object_id=log.object_id,
                occurred_at=log.occurred_at,
                ip=log.ip,
                user_agent=log.user_agent,
                metadata=log.event_metadata or {},
            )
            for log in records
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_count=total,
        total_pages=pages,
    )
