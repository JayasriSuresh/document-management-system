"""
Platform Master Admin Router for Company Onboarding & Tenant Management.

Endpoints (require_platform):
  - POST /api/admin/onboarding/initiate         (Send onboarding form link to prospective company)
  - GET  /api/admin/onboarding                  (List all onboarding applications with filters)
  - GET  /api/admin/onboarding/{id}             (Get full application details & Section A-G data)
  - GET  /api/admin/onboarding/{id}/documents/{doc_type} (Inspect uploaded verification document)
  - POST /api/admin/onboarding/{id}/approve     (Approve application: provisions Company, Branch, & Global Admin)
  - POST /api/admin/onboarding/{id}/request-changes (Request changes: updates status, logs comments, emails applicant)
  - POST /api/admin/onboarding/{id}/reject      (Reject application with reason)
  - GET  /api/admin/companies                   (List all live companies with stats)
  - POST /api/admin/companies/{id}/toggle-status (Suspend or reactivate company)
"""

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.audit import audit
from app.audit.events import (
    COMPANY_CREATE as AUDIT_COMPANY_CREATE,
    MASTER_ADMIN_COMPANY_SUSPEND,
    MASTER_ADMIN_COMPANY_ACTIVATE,
    MASTER_ADMIN_COMPANY_UPDATE,
    MASTER_ADMIN_COMPANY_QUOTA_UPDATE,
    MASTER_ADMIN_SETTINGS_UPDATE,
    MASTER_ADMIN_ONBOARDING_REVIEW,
    ObjectType,
)
from app.auth import get_password_hash
from app.auth.dependencies import require_permission, requires
from app.auth.permissions import PLATFORM_MANAGE
from app.config import settings
from app.context import MasterAdminContext, require_platform
from app.database import get_db
from app.services.currency_service import get_usd_to_inr_rate
from app.models import (
    AccountStatus,
    AIUsageLedger,
    AuditLog,
    Branch,
    Company,
    CompanyOnboarding,
    CompanyStatus,
    Document,
    Invitation,
    OnboardingStatus,
    PlatformSetting,
    User,
    UserRole,
    UserRoleAssignment,
)
from app.routers.onboarding import ONBOARDING_STORAGE_DIR, _to_onboarding_out
from app.schemas import (
    CompanyDetailOut,
    CompanyOnboardingInitiate,
    CompanyOnboardingListItem,
    CompanyOnboardingOut,
    CompanyOut,
    CompanyUpdatePayload,
    DashboardStatsOut,
    GenericMessageResponse,
    RejectPayload,
    RequestChangesPayload,
    SystemSettingsOut,
    SystemSettingsUpdatePayload,
)
from app.services.email_service import email_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _generate_company_code(company_name: str, db: Session) -> str:
    """Generate a clean, unique alphanumeric code for a company."""
    base_code = re.sub(r"[^A-Za-z0-9]+", "_", company_name.strip()).upper().strip("_")
    if not base_code:
        base_code = "COMP"
    base_code = base_code[:30]

    code = base_code
    counter = 1
    while db.query(Company).filter(Company.code == code).first():
        suffix = secrets.token_hex(2).upper()
        code = f"{base_code[:25]}_{suffix}"
        counter += 1
        if counter > 20:
            code = f"COMP_{secrets.token_hex(4).upper()}"
            break
    return code


# ── 1. INITIATE ONBOARDING ───────────────────────────────────────────────────

@router.post("/onboarding/initiate", response_model=CompanyOnboardingOut)
@requires(PLATFORM_MANAGE)
def initiate_company_onboarding(
    payload: CompanyOnboardingInitiate,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Master Admin adds a new company to onboard.
    Creates an onboarding request and dispatches an invitation email with the onboarding form link.
    """
    company_name = payload.company_name.strip()
    contact_name = payload.contact_name.strip()
    contact_email = payload.contact_email.strip().lower()

    if not company_name or not contact_name or not contact_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company Name, Contact Person Name, and Contact Person Email are all required.",
        )

    # Generate secure unique token
    token = secrets.token_urlsafe(32)

    onboarding = CompanyOnboarding(
        token=token,
        status=OnboardingStatus.PENDING_SUBMISSION,
        initial_company_name=company_name,
        legal_company_name=company_name,
        contact_name=contact_name,
        contact_email=contact_email,
        auth_contact_name=contact_name,
        auth_contact_email=contact_email,
        admin_name=contact_name,
        admin_email=contact_email,
        created_by_admin_id=admin_ctx.admin_id,
        uploaded_documents={},
        review_history=[
            {
                "action": "initiated",
                "admin_name": admin_ctx.admin_name,
                "timestamp": datetime.utcnow().isoformat(),
                "note": f"Onboarding link generated and dispatched to {contact_email}",
            }
        ],
    )

    db.add(onboarding)
    db.flush()

    audit.record_event(
        db=db,
        action="onboarding.initiate",
        request=request,
        auth_context=admin_ctx,
        object_type="onboarding",
        object_id=onboarding.id,
        metadata={
            "company_name": company_name,
            "contact_email": contact_email,
        },
    )
    db.commit()
    db.refresh(onboarding)

    # Dispatch email
    email_service.send_onboarding_invitation_email(
        to_email=contact_email,
        contact_name=contact_name,
        company_name=company_name,
        raw_token=token,
    )

    return _to_onboarding_out(onboarding)


# ── 2. LIST ONBOARDINGS ──────────────────────────────────────────────────────

@router.get("/onboarding", response_model=List[CompanyOnboardingListItem])
@requires(PLATFORM_MANAGE)
def list_onboardings(
    status_filter: Optional[str] = Query(None, alias="status"),
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """List all company onboarding records with optional status filtering."""
    query = db.query(CompanyOnboarding)

    if status_filter and status_filter.lower() != "all":
        try:
            target_status = OnboardingStatus(status_filter.lower())
            query = query.filter(CompanyOnboarding.status == target_status)
        except ValueError:
            pass

    records = query.order_by(CompanyOnboarding.created_at.desc()).all()
    return records


# ── 3. GET SINGLE ONBOARDING DETAILS ─────────────────────────────────────────

@router.get("/onboarding/{onboarding_id}", response_model=CompanyOnboardingOut)
@requires(PLATFORM_MANAGE)
def get_onboarding_details(
    onboarding_id: int,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Get full details of a specific onboarding record."""
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.id == onboarding_id).first()
    if not onboarding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding record not found.")
    return _to_onboarding_out(onboarding)


# ── 4. INSPECT UPLOADED DOCUMENT ─────────────────────────────────────────────

@router.get("/onboarding/{onboarding_id}/documents/{document_type}")
@requires(PLATFORM_MANAGE)
def inspect_uploaded_document(
    onboarding_id: int,
    document_type: str,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Download/inspect an uploaded verification document."""
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.id == onboarding_id).first()
    if not onboarding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding record not found.")

    docs = onboarding.uploaded_documents or {}
    if document_type not in docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested document not found.")

    doc_meta = docs[document_type]
    file_path = ONBOARDING_STORAGE_DIR / doc_meta["storage_key"]
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File is missing from disk.")

    return FileResponse(
        path=file_path,
        media_type=doc_meta.get("mime_type", "application/octet-stream"),
        filename=doc_meta.get("filename", f"{document_type}.bin"),
        content_disposition_type="attachment",
    )


# ── 5. REQUEST CHANGES ───────────────────────────────────────────────────────

@router.post("/onboarding/{onboarding_id}/request-changes", response_model=GenericMessageResponse)
@requires(PLATFORM_MANAGE)
def request_onboarding_changes(
    onboarding_id: int,
    payload: RequestChangesPayload,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Master Admin requests modifications from applicant.
    Moves status to CHANGES_REQUESTED, updates comments, and sends email to contact person.
    """
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.id == onboarding_id).first()
    if not onboarding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding record not found.")

    if onboarding.status == OnboardingStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot request changes for an already approved company.",
        )

    comments = payload.comments.strip()
    if not comments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review comments explaining requested changes are required.",
        )

    onboarding.status = OnboardingStatus.CHANGES_REQUESTED
    onboarding.review_comments = comments
    onboarding.reviewed_at = datetime.utcnow()

    history = onboarding.review_history or []
    history.append({
        "action": "changes_requested",
        "admin_name": admin_ctx.admin_name,
        "comment": comments,
        "timestamp": datetime.utcnow().isoformat(),
    })
    onboarding.review_history = history
    flag_modified(onboarding, "review_history")

    audit.record_event(
        db=db,
        action=MASTER_ADMIN_ONBOARDING_REVIEW,
        request=request,
        auth_context=admin_ctx,
        object_type="onboarding",
        object_id=onboarding.id,
        metadata={
            "review_decision": "changes_requested",
            "comments": comments,
        },
    )
    db.commit()

    # Dispatch email to contact person
    email_service.send_onboarding_changes_requested_email(
        to_email=onboarding.contact_email,
        contact_name=onboarding.contact_name,
        company_name=onboarding.legal_company_name or onboarding.initial_company_name,
        review_comment=comments,
        raw_token=onboarding.token,
    )

    return GenericMessageResponse(
        message=f"Change request successfully submitted. An email with your feedback has been sent to {onboarding.contact_email}."
    )


# ── 6. REJECT APPLICATION ────────────────────────────────────────────────────

@router.post("/onboarding/{onboarding_id}/reject", response_model=GenericMessageResponse)
@requires(PLATFORM_MANAGE)
def reject_onboarding(
    onboarding_id: int,
    payload: RejectPayload,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Master Admin rejects onboarding application.
    """
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.id == onboarding_id).first()
    if not onboarding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding record not found.")

    if onboarding.status == OnboardingStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reject an already approved company.",
        )

    reason = payload.reason.strip() if payload.reason else "Application does not meet onboarding criteria."

    onboarding.status = OnboardingStatus.REJECTED
    onboarding.review_comments = reason
    onboarding.reviewed_at = datetime.utcnow()

    history = onboarding.review_history or []
    history.append({
        "action": "rejected",
        "admin_name": admin_ctx.admin_name,
        "comment": reason,
        "timestamp": datetime.utcnow().isoformat(),
    })
    onboarding.review_history = history
    flag_modified(onboarding, "review_history")

    audit.record_event(
        db=db,
        action=MASTER_ADMIN_ONBOARDING_REVIEW,
        request=request,
        auth_context=admin_ctx,
        object_type="onboarding",
        object_id=onboarding.id,
        metadata={
            "review_decision": "rejected",
            "reason": reason,
        },
    )
    db.commit()

    # Dispatch rejection email
    email_service.send_onboarding_rejected_email(
        to_email=onboarding.contact_email,
        contact_name=onboarding.contact_name,
        company_name=onboarding.legal_company_name or onboarding.initial_company_name,
        reason=reason,
    )

    return GenericMessageResponse(message="Application has been rejected.")


# ── 7. APPROVE APPLICATION ───────────────────────────────────────────────────

@router.post("/onboarding/{onboarding_id}/approve", response_model=GenericMessageResponse)
@requires(PLATFORM_MANAGE)
def approve_onboarding(
    onboarding_id: int,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Master Admin approves the application:
      1. Provisions Company record in database
      2. Provisions default Primary Branch ("Headquarters" / "Main Office")
      3. Provisions optional branches if indicated in Section E
      4. Provisions First Company Administrator User (GLOBAL_ADMIN)
      5. Marks Onboarding status as APPROVED
      6. Sends welcome / approval email with Company Portal login link
    """
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.id == onboarding_id).first()
    if not onboarding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding record not found.")

    if onboarding.status == OnboardingStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Application is already approved.")

    company_name = (onboarding.legal_company_name or onboarding.initial_company_name).strip()
    company_code = _generate_company_code(company_name, db)

    address_full = f"{onboarding.address_line1 or ''}, {onboarding.city or ''}, {onboarding.state or ''} - {onboarding.pincode or ''}".strip(", -")

    # Load system defaults if configured
    s_defaults = db.query(PlatformSetting).filter(PlatformSetting.key == "system_defaults").first()
    sys_def = s_defaults.value if s_defaults and isinstance(s_defaults.value, dict) else {}
    max_branches = int(sys_def.get("default_max_branches", 5))
    max_users = int(sys_def.get("default_max_users", 20))
    storage_limit = int(sys_def.get("default_storage_limit_bytes", 5368709120))
    monthly_ai_budget = int(sys_def.get("default_monthly_ai_budget_cents", 2500))
    rate = get_usd_to_inr_rate(db)
    monthly_ai_budget_inr = round((monthly_ai_budget / 100.0) * rate, 2)

    pan_clean = (onboarding.pan_number or "").strip().upper() or None
    gstin_clean = (onboarding.gstin or "").strip().upper() or None
    trade_name_clean = (onboarding.trade_name or "").strip() or None
    website_clean = (onboarding.company_website or "").strip() or None
    contact_person_clean = (onboarding.auth_contact_name or onboarding.contact_name or "").strip() or None
    contact_email_clean = (onboarding.auth_contact_email or onboarding.contact_email or "").strip().lower() or None
    contact_phone_clean = (onboarding.auth_contact_mobile or "").strip() or None

    # 1. Create Company with typed quota limits and enforced mandatory MFA
    company = Company(
        name=company_name,
        code=company_code,
        status=CompanyStatus.ACTIVE,
        display_name=trade_name_clean,
        pan=pan_clean,
        gstin=gstin_clean,
        website=website_clean,
        contact_person=contact_person_clean,
        contact_email=contact_email_clean,
        contact_phone=contact_phone_clean,
        address=address_full,
        max_branches=max_branches,
        max_users=max_users,
        storage_limit_bytes=storage_limit,
        monthly_ai_budget_cents=monthly_ai_budget,
        monthly_ai_budget_inr=monthly_ai_budget_inr,
        reporting_currency="INR",
        ai_budget_spent_cents=0,
        ai_budget_spent_inr=0.0,
        mfa_required_for_all=True,
        limits={
            "expected_monthly_volume": onboarding.expected_monthly_volume,
            "business_type": onboarding.business_type,
            "pan": pan_clean,
            "cin": onboarding.cin,
            "llpin": onboarding.llpin,
            "udyam_number": onboarding.udyam_number,
            "tan": onboarding.tan,
            "year_of_establishment": onboarding.year_of_establishment,
            "business_description": onboarding.business_description,
        },
    )
    db.add(company)
    db.flush()

    # Create default GST Registration if valid GSTIN provided
    gst_reg_id = None
    if gstin_clean and len(gstin_clean) == 15:
        from app.models import GstRegistration
        from app.services.gstin_validator import INDIAN_GST_STATE_CODES
        state_code = gstin_clean[:2]
        state_name = INDIAN_GST_STATE_CODES.get(state_code, onboarding.state or "Unknown")
        gst_reg = GstRegistration(
            company_id=company.id,
            gstin=gstin_clean,
            legal_name=company_name,
            trade_name=trade_name_clean,
            state_code=state_code,
            state_name=state_name,
            registered_address=address_full,
            is_default=True,
            is_active=True,
        )
        db.add(gst_reg)
        db.flush()
        gst_reg_id = gst_reg.id

    # 2. Create Primary Branch
    primary_branch = Branch(
        company_id=company.id,
        name="Headquarters",
        code="HQ",
        branch_type="Head Office",
        branch_email=contact_email_clean,
        branch_contact_number=contact_phone_clean,
        address_line1=onboarding.address_line1,
        address_line2=onboarding.address_line2,
        city=onboarding.city,
        district=onboarding.district,
        state=onboarding.state,
        pincode=onboarding.pincode,
        country=onboarding.country or "India",
        gst_registered=bool(gstin_clean),
        gstin=gstin_clean,
        gst_type=onboarding.gst_type or ("Regular" if gstin_clean else None),
        gst_registration_id=gst_reg_id,
        status="active",
    )
    db.add(primary_branch)
    db.flush()

    # Create additional branches if specified in Section E
    if onboarding.has_multiple_branches and onboarding.branch_details:
        for idx, b_item in enumerate(onboarding.branch_details):
            b_name = str(b_item.get("name") if isinstance(b_item, dict) else b_item).strip()
            if b_name and b_name.lower() != "headquarters":
                b_code = re.sub(r"[^A-Za-z0-9]+", "", b_name).upper()[:10] or f"BR{idx+1}"
                # Ensure uniqueness
                existing_branch = db.query(Branch).filter(Branch.company_id == company.id, Branch.code == b_code).first()
                if not existing_branch:
                    add_branch = Branch(company_id=company.id, name=b_name, code=b_code)
                    db.add(add_branch)
        db.flush()

    # 3. Create First Company Administrator User (GLOBAL_ADMIN)
    admin_email = (onboarding.admin_email or onboarding.contact_email).strip().lower()
    existing_user = db.query(User).filter(User.email == admin_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A user with email '{admin_email}' already exists in the system.",
        )

    # Secure Password Lifecycle: Support pre-set password if provided, or generate random temporary hash
    must_change = False
    if onboarding.admin_password_hash:
        pwd_hash = onboarding.admin_password_hash
    else:
        pwd_hash = get_password_hash(secrets.token_urlsafe(32))
        must_change = True

    admin_user = User(
        company_id=company.id,
        branch_id=primary_branch.id,
        name=onboarding.admin_name or onboarding.contact_name,
        email=admin_email,
        password_hash=pwd_hash,
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
        must_change_password=must_change,
    )
    db.add(admin_user)
    db.flush()

    # Issue an Invitation Token with 72h expiry
    raw_invite_token = secrets.token_hex(32)
    invite_hash = hashlib.sha256(raw_invite_token.encode("utf-8")).hexdigest()
    invite_record = Invitation(
        email=admin_email,
        company_id=company.id,
        branch_id=primary_branch.id,
        invited_role=UserRole.GLOBAL_ADMIN,
        token_hash=invite_hash,
        invited_by=None,
        expires_at=datetime.utcnow() + timedelta(hours=72),
        accepted_at=datetime.utcnow() if admin_user.status == AccountStatus.ACTIVE and not must_change else None,
        created_at=datetime.utcnow(),
    )
    db.add(invite_record)

    # Module 4: Provision company-level GLOBAL_ADMIN role assignment
    db.add(UserRoleAssignment(
        user_id=admin_user.id,
        role="GLOBAL_ADMIN",
        scope_type="company",
        scope_id=company.id,
    ))

    # 4. Update Onboarding Record
    onboarding.status = OnboardingStatus.APPROVED
    onboarding.company_id = company.id
    onboarding.reviewed_at = datetime.utcnow()

    history = onboarding.review_history or []
    history.append({
        "action": "approved",
        "admin_name": admin_ctx.admin_name,
        "company_id": company.id,
        "company_code": company_code,
        "timestamp": datetime.utcnow().isoformat(),
    })
    onboarding.review_history = history
    flag_modified(onboarding, "review_history")

    audit.record_event(
        db=db,
        action=MASTER_ADMIN_ONBOARDING_REVIEW,
        request=request,
        auth_context=admin_ctx,
        object_type="onboarding",
        object_id=onboarding.id,
        metadata={
            "review_decision": "approved",
            "company_id": company.id,
            "company_code": company_code,
        },
    )
    audit.record_event(
        db=db,
        action=AUDIT_COMPANY_CREATE,
        request=request,
        auth_context=admin_ctx,
        object_type=ObjectType.COMPANY,
        object_id=company.id,
        metadata={
            "company_name": company.name,
            "company_code": company.code,
            "admin_email": admin_user.email,
        },
    )
    db.commit()

    # 5. Dispatch Approval Email
    try:
        email_service.send_onboarding_approved_email(
            to_email=onboarding.contact_email,
            contact_name=onboarding.contact_name,
            company_name=company.name,
            admin_email=admin_user.email,
        )
    except Exception as email_err:
        logger.warning("Failed to deliver onboarding approval notification email to %s: %s", onboarding.contact_email, email_err)

    return GenericMessageResponse(
        message=f"Company '{company.name}' successfully approved and provisioned! First Administrator account created for '{admin_user.email}'."
    )


# ── 8. PLATFORM DASHBOARD AGGREGATION ─────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardStatsOut)
@requires(PLATFORM_MANAGE)
def get_platform_dashboard(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Database-side aggregated metrics for the Platform Root Dashboard.
    """
    total_companies = db.query(func.count(Company.id)).scalar() or 0
    active_companies = db.query(func.count(Company.id)).filter(Company.status == CompanyStatus.ACTIVE).scalar() or 0
    suspended_companies = db.query(func.count(Company.id)).filter(Company.status == CompanyStatus.SUSPENDED).scalar() or 0
    total_branches = db.query(func.count(Branch.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).filter(User.status == AccountStatus.ACTIVE).scalar() or 0
    total_documents = db.query(func.count(Document.id)).filter(Document.deleted_at.is_(None)).scalar() or 0
    total_storage_bytes = db.query(func.coalesce(func.sum(Document.file_size), 0)).filter(Document.deleted_at.is_(None)).scalar() or 0

    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_ai_spent_cents = db.query(func.coalesce(func.sum(AIUsageLedger.cost_cents), 0)).filter(
        AIUsageLedger.created_at >= start_of_month,
        AIUsageLedger.status == "success",
    ).scalar() or 0

    pending_onboardings = db.query(func.count(CompanyOnboarding.id)).filter(
        CompanyOnboarding.status.in_([
            OnboardingStatus.PENDING_SUBMISSION,
            OnboardingStatus.SUBMITTED,
            OnboardingStatus.CHANGES_REQUESTED,
        ])
    ).scalar() or 0

    # Recent 10 platform audit logs
    recent_logs = db.query(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(10).all()
    recent_activity = []
    for log in recent_logs:
        recent_activity.append({
            "id": log.id,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
            "action": log.action,
            "actor_type": log.actor_type,
            "actor_id": log.actor_id,
            "object_type": log.object_type,
            "object_id": log.object_id,
            "company_id": log.company_id,
            "ip": log.ip,
        })

    rate = get_usd_to_inr_rate(db)
    total_ai_spent_inr = round((int(total_ai_spent_cents) / 100.0) * rate, 2)

    return DashboardStatsOut(
        total_companies=total_companies,
        active_companies=active_companies,
        suspended_companies=suspended_companies,
        total_branches=total_branches,
        total_users=total_users,
        total_documents=total_documents,
        total_storage_bytes=int(total_storage_bytes),
        total_ai_spent_cents=int(total_ai_spent_cents),
        total_ai_spent_inr=total_ai_spent_inr,
        exchange_rate=rate,
        pending_onboardings=pending_onboardings,
        recent_activity=recent_activity,
    )


# ── 9. LIVE COMPANIES DIRECTORY (O(1) OPTIMIZED) ─────────────────────────────

@router.get("/companies")
@requires(PLATFORM_MANAGE)
def list_companies(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    List all registered companies along with quotas and usage metrics.
    Uses database-side GROUP BY aggregations to eliminate N+1 queries.
    """
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    if not companies:
        return []

    # Single aggregate query for branch counts
    branch_counts = dict(
        db.query(Branch.company_id, func.count(Branch.id))
        .group_by(Branch.company_id)
        .all()
    )

    # Single aggregate query for active users
    user_counts = dict(
        db.query(User.company_id, func.count(User.id))
        .filter(User.status == AccountStatus.ACTIVE)
        .group_by(User.company_id)
        .all()
    )

    # Single aggregate query for document count and total storage
    doc_stats_raw = (
        db.query(
            Document.company_id,
            func.count(Document.id),
            func.coalesce(func.sum(Document.file_size), 0),
        )
        .filter(Document.deleted_at.is_(None))
        .group_by(Document.company_id)
        .all()
    )
    doc_counts = {r[0]: r[1] for r in doc_stats_raw}
    storage_used = {r[0]: int(r[2]) for r in doc_stats_raw}

    # Single aggregate query for current month AI spend
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ai_spend_raw = (
        db.query(AIUsageLedger.company_id, func.coalesce(func.sum(AIUsageLedger.cost_cents), 0))
        .filter(AIUsageLedger.created_at >= start_of_month, AIUsageLedger.status == "success")
        .group_by(AIUsageLedger.company_id)
        .all()
    )
    ai_spend = {r[0]: int(r[1]) for r in ai_spend_raw}

    # Map linked onboarding IDs
    onboarding_map = dict(
        db.query(CompanyOnboarding.company_id, CompanyOnboarding.id)
        .filter(CompanyOnboarding.company_id.isnot(None))
        .all()
    )

    rate = get_usd_to_inr_rate(db)
    results = []
    for c in companies:
        cents = ai_spend.get(c.id, 0)
        results.append({
            "id": c.id,
            "name": c.name,
            "code": c.code,
            "status": c.status.value,
            "gstin": c.gstin,
            "address": c.address,
            "mfa_required_for_all": c.mfa_required_for_all,
            "max_branches": c.max_branches,
            "max_users": c.max_users,
            "storage_limit_bytes": c.storage_limit_bytes,
            "monthly_ai_budget_cents": c.monthly_ai_budget_cents,
            "monthly_ai_budget_inr": c.monthly_ai_budget_inr or round(((c.monthly_ai_budget_cents or 0) / 100.0) * rate, 2),
            "branch_count": branch_counts.get(c.id, 0),
            "user_count": user_counts.get(c.id, 0),
            "document_count": doc_counts.get(c.id, 0),
            "storage_used_bytes": storage_used.get(c.id, 0),
            "ai_spent_cents": cents,
            "ai_spent_inr": round(float(c.ai_budget_spent_inr or ((cents / 100.0) * rate)), 2),
            "reporting_currency": c.reporting_currency or "INR",
            "onboarding_id": onboarding_map.get(c.id),
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        })

    return results


# ── 10. GET SINGLE COMPANY DETAILS & QUOTAS ───────────────────────────────────

@router.get("/companies/{company_id}", response_model=CompanyDetailOut)
@requires(PLATFORM_MANAGE)
def get_company_detail(
    company_id: int,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Get full metadata and live resource usage for a specific company.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    branch_count = db.query(func.count(Branch.id)).filter(Branch.company_id == company.id).scalar() or 0
    user_count = db.query(func.count(User.id)).filter(User.company_id == company.id, User.status == AccountStatus.ACTIVE).scalar() or 0
    doc_count = db.query(func.count(Document.id)).filter(Document.company_id == company.id, Document.deleted_at.is_(None)).scalar() or 0
    storage_used_bytes = db.query(func.coalesce(func.sum(Document.file_size), 0)).filter(
        Document.company_id == company.id,
        Document.deleted_at.is_(None),
    ).scalar() or 0

    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ai_spent_cents = db.query(func.coalesce(func.sum(AIUsageLedger.cost_cents), 0)).filter(
        AIUsageLedger.company_id == company.id,
        AIUsageLedger.created_at >= start_of_month,
        AIUsageLedger.status == "success",
    ).scalar() or 0

    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.company_id == company.id).first()
    rate = get_usd_to_inr_rate(db)

    return CompanyDetailOut(
        id=company.id,
        name=company.name,
        code=company.code,
        status=company.status.value,
        display_name=company.display_name or (onboarding.trade_name if onboarding else None),
        logo_url=company.logo_url,
        pan=company.pan or (onboarding.pan_number if onboarding else None),
        pan_number=company.pan or (onboarding.pan_number if onboarding else None),
        gstin=company.gstin or (onboarding.gstin if onboarding else None),
        website=company.website or (onboarding.company_website if onboarding else None),
        company_website=company.website or (onboarding.company_website if onboarding else None),
        contact_person=company.contact_person or (onboarding.auth_contact_name if onboarding else (onboarding.contact_name if onboarding else None)),
        contact_email=company.contact_email or (onboarding.auth_contact_email if onboarding else (onboarding.contact_email if onboarding else None)),
        contact_phone=company.contact_phone or (onboarding.auth_contact_mobile if onboarding else None),
        address=company.address,
        registered_address=company.address,
        mfa_required_for_all=company.mfa_required_for_all,
        max_branches=company.max_branches,
        max_users=company.max_users,
        storage_limit_bytes=company.storage_limit_bytes,
        monthly_ai_budget_cents=company.monthly_ai_budget_cents,
        ai_budget_spent_cents=int(ai_spent_cents),
        monthly_ai_budget_inr=company.monthly_ai_budget_inr or round(((company.monthly_ai_budget_cents or 0) / 100.0) * rate, 2),
        ai_budget_spent_inr=float(company.ai_budget_spent_inr or round((int(ai_spent_cents) / 100.0) * rate, 2)),
        reporting_currency=company.reporting_currency or "INR",
        branch_count=branch_count,
        user_count=user_count,
        document_count=doc_count,
        storage_used_bytes=int(storage_used_bytes),
        ai_spent_cents=int(ai_spent_cents),
        created_at=company.created_at,
        updated_at=company.updated_at,
        onboarding_id=onboarding.id if onboarding else None,
    )


# ── 10B. GET COMPANY ONBOARDING DOSSIER ───────────────────────────────────────

@router.get("/companies/{company_id}/onboarding", response_model=Optional[CompanyOnboardingOut])
@requires(PLATFORM_MANAGE)
def get_company_onboarding_dossier(
    company_id: int,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Get the complete onboarding dossier (submitted form data, compliance identifiers,
    document metadata, and review history) for an onboarded company.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.company_id == company.id).first()
    if not onboarding:
        return None
    return _to_onboarding_out(onboarding)


# ── 11. UPDATE COMPANY DETAILS & QUOTAS ───────────────────────────────────────

@router.put("/companies/{company_id}", response_model=CompanyDetailOut)
@requires(PLATFORM_MANAGE)
def update_company(
    company_id: int,
    payload: CompanyUpdatePayload,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Update company metadata, status, MFA policy, and resource quota limits.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    old_values = {
        "name": company.name,
        "status": company.status.value,
        "gstin": company.gstin,
        "address": company.address,
        "mfa_required_for_all": company.mfa_required_for_all,
        "max_branches": company.max_branches,
        "max_users": company.max_users,
        "storage_limit_bytes": company.storage_limit_bytes,
        "monthly_ai_budget_cents": company.monthly_ai_budget_cents,
    }

    if payload.name is not None and payload.name.strip():
        company.name = payload.name.strip()
    if payload.status is not None:
        try:
            company.status = CompanyStatus(payload.status.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid company status: {payload.status}")
    if payload.gstin is not None:
        company.gstin = payload.gstin.strip().upper() or None
    if payload.address is not None:
        company.address = payload.address.strip() or None
    if payload.mfa_required_for_all is not None:
        company.mfa_required_for_all = payload.mfa_required_for_all
    if payload.max_branches is not None:
        company.max_branches = payload.max_branches
    if payload.max_users is not None:
        company.max_users = payload.max_users
    if payload.storage_limit_bytes is not None:
        company.storage_limit_bytes = payload.storage_limit_bytes
    if payload.monthly_ai_budget_cents is not None:
        company.monthly_ai_budget_cents = payload.monthly_ai_budget_cents
        rate = get_usd_to_inr_rate(db)
        company.monthly_ai_budget_inr = round((payload.monthly_ai_budget_cents / 100.0) * rate, 2)

    company.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(company)

    audit.record_event(
        db=db,
        action=MASTER_ADMIN_COMPANY_UPDATE,
        request=request,
        auth_context=admin_ctx,
        object_type=ObjectType.COMPANY,
        object_id=company.id,
        metadata={
            "company_name": company.name,
            "old_values": old_values,
            "new_values": {
                "name": company.name,
                "status": company.status.value,
                "gstin": company.gstin,
                "address": company.address,
                "mfa_required_for_all": company.mfa_required_for_all,
                "max_branches": company.max_branches,
                "max_users": company.max_users,
                "storage_limit_bytes": company.storage_limit_bytes,
                "monthly_ai_budget_cents": company.monthly_ai_budget_cents,
            },
        },
    )
    db.commit()

    return get_company_detail(company_id=company.id, admin_ctx=admin_ctx, db=db)


# ── 12. SUSPEND / REACTIVATE COMPANY ─────────────────────────────────────────

@router.post("/companies/{company_id}/toggle-status")
@requires(PLATFORM_MANAGE)
def toggle_company_status(
    company_id: int,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """Toggle company active / suspended status."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    if company.status == CompanyStatus.ACTIVE:
        company.status = CompanyStatus.SUSPENDED
        msg = f"Company '{company.name}' has been suspended. Tenant users are now blocked from accessing documents."
    else:
        company.status = CompanyStatus.ACTIVE
        msg = f"Company '{company.name}' has been reactivated."

    action = MASTER_ADMIN_COMPANY_SUSPEND if company.status == CompanyStatus.SUSPENDED else MASTER_ADMIN_COMPANY_ACTIVATE
    audit.record_event(
        db=db,
        action=action,
        request=request,
        auth_context=admin_ctx,
        object_type=ObjectType.COMPANY,
        object_id=company.id,
        metadata={
            "company_name": company.name,
            "company_code": company.code,
            "status": company.status.value,
        },
    )
    db.commit()
    return {"message": msg, "status": company.status.value}


# ── 13. SYSTEM SETTINGS & PROVIDER CONTROLS ───────────────────────────────────

DEFAULT_SYSTEM_DEFAULTS = {
    "default_max_branches": 5,
    "default_max_users": 20,
    "default_storage_limit_bytes": 5368709120,  # 5 GB
    "default_monthly_ai_budget_cents": 2500,     # $25.00
}

DEFAULT_AI_PROVIDERS = {
    "gemini": {
        "enabled": True,
        "display_name": "Google Gemini",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro"],
        "default_model": "gemini-2.0-flash",
    },
    "gpt": {
        "enabled": False,
        "display_name": "OpenAI GPT",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-4o-mini",
    },
    "claude": {
        "enabled": False,
        "display_name": "Anthropic Claude",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
        "default_model": "claude-3-5-sonnet-20241022",
    },
}


@router.get("/settings", response_model=SystemSettingsOut)
@requires(PLATFORM_MANAGE)
def get_system_settings(
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Get platform-wide default quotas, AI provider availability, and MFA enforcement policies.
    Never exposes raw API keys.
    """
    s_defaults = db.query(PlatformSetting).filter(PlatformSetting.key == "system_defaults").first()
    system_defaults = s_defaults.value if s_defaults and isinstance(s_defaults.value, dict) else DEFAULT_SYSTEM_DEFAULTS

    s_providers = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_providers").first()
    ai_providers = s_providers.value if s_providers and isinstance(s_providers.value, dict) else DEFAULT_AI_PROVIDERS

    s_mfa = db.query(PlatformSetting).filter(PlatformSetting.key == "mfa_policy").first()
    mfa_policy = s_mfa.value if s_mfa and isinstance(s_mfa.value, dict) else {
        "enforce_master_admin": True,
        "enforce_company_admin": False,
        "enforce_all": False,
    }

    return SystemSettingsOut(
        system_defaults=system_defaults,
        ai_providers=ai_providers,
        mfa_policy=mfa_policy,
    )


@router.put("/settings", response_model=SystemSettingsOut)
@requires(PLATFORM_MANAGE)
def update_system_settings(
    payload: SystemSettingsUpdatePayload,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
    db: Session = Depends(get_db),
):
    """
    Update platform default quotas and AI provider controls while preserving existing policies.
    """
    if payload.system_defaults is not None:
        rec = db.query(PlatformSetting).filter(PlatformSetting.key == "system_defaults").first()
        if not rec:
            rec = PlatformSetting(
                key="system_defaults",
                value=payload.system_defaults,
                updated_by=admin_ctx.admin_id,
            )
            db.add(rec)
        else:
            rec.value = payload.system_defaults
            rec.updated_at = datetime.utcnow()
            rec.updated_by = admin_ctx.admin_id

        # If requested, cascade updated quotas to all existing companies
        if payload.apply_to_existing_companies:
            new_branches = payload.system_defaults.get("default_max_branches")
            new_users = payload.system_defaults.get("default_max_users")
            new_storage = payload.system_defaults.get("default_storage_limit_bytes")
            new_budget = payload.system_defaults.get("default_monthly_ai_budget_cents")
            all_comps = db.query(Company).all()
            for comp in all_comps:
                if new_branches is not None:
                    comp.max_branches = int(new_branches)
                if new_users is not None:
                    comp.max_users = int(new_users)
                if new_storage is not None:
                    comp.storage_limit_bytes = int(new_storage)
                if new_budget is not None:
                    comp.monthly_ai_budget_cents = int(new_budget)
                    rate = get_usd_to_inr_rate(db)
                    comp.monthly_ai_budget_inr = round((int(new_budget) / 100.0) * rate, 2)
                comp.updated_at = datetime.utcnow()

    if payload.ai_providers is not None:
        rec = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_providers").first()
        if not rec:
            rec = PlatformSetting(
                key="ai_providers",
                value=payload.ai_providers,
                updated_by=admin_ctx.admin_id,
            )
            db.add(rec)
        else:
            rec.value = payload.ai_providers
            rec.updated_at = datetime.utcnow()
            rec.updated_by = admin_ctx.admin_id

    db.commit()

    audit.record_event(
        db=db,
        action=MASTER_ADMIN_SETTINGS_UPDATE,
        request=request,
        auth_context=admin_ctx,
        object_type=ObjectType.SECURITY_POLICY,
        object_id="platform_settings",
        metadata={
            "updated_sections": [
                k for k, v in [("system_defaults", payload.system_defaults), ("ai_providers", payload.ai_providers)] if v is not None
            ],
        },
    )

    return get_system_settings(admin_ctx=admin_ctx, db=db)


