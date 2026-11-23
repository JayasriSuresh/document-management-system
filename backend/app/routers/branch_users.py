"""
Module 15 – Branch Admin User Management Router.

Allows authorized Branch Administrators to view, invite, edit, activate, and deactivate
STAFF and UPLOADER accounts within their assigned administrative branch scope.
Preserves tenant isolation, role boundaries, quota limits, session revocation, and audit logging.
Company Administrators retain company-wide oversight.
"""

import hashlib
import logging
import math
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.audit import (
    AUTH_INVITATION_CREATE,
    AUTH_INVITATION_REVOKE,
    USER_CREATE,
    USER_DEACTIVATE,
    USER_REACTIVATE,
    USER_UPDATE,
    audit,
)
from app.audit.events import ObjectType
from app.auth.dependencies import require_permission, requires
from app.auth.permissions import (
    USER_ACTIVATE_BRANCH,
    USER_DEACTIVATE_BRANCH,
    USER_INVITE_BRANCH,
    USER_UPDATE_BRANCH,
    USER_VIEW_BRANCH,
)
from app.config import settings
from app.context import AuthContext
from app.database import get_db
from app.models import (
    AccountStatus,
    Branch,
    Company,
    Invitation,
    User,
    UserRole,
    UserRoleAssignment,
)
from app.schemas import (
    BranchSummaryOut,
    BranchUserInviteRequest,
    BranchUserUpdateRequest,
    CompanyInvitationItem,
    CompanyUserItem,
    CompanyUsersPaginationResponse,
    GenericMessageResponse,
)
from app.services.email_service import email_service
from app.services.invitation_service import hash_token
from app.services.mfa_service import MfaService
from app.services.session_service import session_service

logger = logging.getLogger("dms.routers.branch_users")

router = APIRouter(prefix="/api/branch", tags=["branch_users"])


# ── Helper Utilities ─────────────────────────────────────────────────────────

def get_caller_authorized_branch_ids(auth_ctx: AuthContext, db: Session) -> Set[int]:
    """
    Resolves the set of branch IDs for which the caller possesses administrative authority.
    - Company Admin (GLOBAL_ADMIN): All branches within their company.
    - Branch Admin (ADMIN): Primary branch_id plus any secondary branch with an active ADMIN assignment.
    - Non-admins: Empty set.
    """
    if auth_ctx.is_global_admin or "company.manage" in auth_ctx.permissions:
        return {
            b_id
            for (b_id,) in db.query(Branch.id)
            .filter(Branch.company_id == auth_ctx.company_id)
            .all()
        }

    is_admin = auth_ctx.role == UserRole.ADMIN
    if not is_admin:
        for a in auth_ctx.assignments:
            if isinstance(a, dict) and a.get("role") in ("ADMIN", "GLOBAL_ADMIN"):
                is_admin = True
                break

    if not is_admin:
        return set()

    authorized: Set[int] = set()
    if auth_ctx.branch_id:
        authorized.add(auth_ctx.branch_id)

    for a in auth_ctx.assignments:
        if isinstance(a, dict) and a.get("scope_type") == "branch" and a.get("scope_id"):
            if a.get("role") in ("ADMIN", "GLOBAL_ADMIN"):
                authorized.add(int(a["scope_id"]))

    return authorized


def is_target_admin(user: User, db: Session) -> bool:
    """
    Checks if a target user holds an administrative role (GLOBAL_ADMIN or ADMIN)
    via their user.role or any active UserRoleAssignment.
    """
    if user.role in (UserRole.GLOBAL_ADMIN, UserRole.ADMIN):
        return True

    has_admin_assign = (
        db.query(UserRoleAssignment.id)
        .filter(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.role.in_(("GLOBAL_ADMIN", "ADMIN")),
        )
        .first()
    )
    return has_admin_assign is not None


def get_target_user_branch_ids(user: User, db: Session) -> Set[int]:
    """
    Returns the set of all branch IDs assigned to the target user (primary branch + assignments).
    """
    branches: Set[int] = set()
    if user.branch_id:
        branches.add(user.branch_id)

    assignments = (
        db.query(UserRoleAssignment.scope_id)
        .filter(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.scope_type == "branch",
        )
        .all()
    )
    for a in assignments:
        if a.scope_id:
            branches.add(a.scope_id)

    return branches


# ── 1. List Authorized Branches ─────────────────────────────────────────────

@router.get("/branches", response_model=List[BranchSummaryOut])
@requires(USER_VIEW_BRANCH)
def list_authorized_branches(
    auth_ctx: AuthContext = Depends(require_permission(USER_VIEW_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    List branches the administrator is authorized to manage.
    Used by branch selector dropdowns in branch-level user management.
    """
    auth_ctx.assert_active_company()
    authorized_ids = get_caller_authorized_branch_ids(auth_ctx, db)
    if not authorized_ids:
        return []

    branches = (
        db.query(Branch)
        .filter(Branch.id.in_(authorized_ids), Branch.company_id == auth_ctx.company_id)
        .order_by(Branch.name.asc())
        .all()
    )
    return [
        BranchSummaryOut(
            id=b.id,
            name=b.name,
            code=b.code,
            status=b.status or "active",
        )
        for b in branches
    ]


# ── 2. List Branch Users ────────────────────────────────────────────────────

@router.get("/users", response_model=CompanyUsersPaginationResponse)
@requires(USER_VIEW_BRANCH)
def list_branch_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    branch_id: Optional[int] = Query(default=None),
    role: Optional[str] = Query(default=None),
    user_status: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    auth_ctx: AuthContext = Depends(require_permission(USER_VIEW_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    List users belonging strictly to the caller's authorized administrative branch scope.
    Includes primary branch users and relevant secondary assignments.
    Filters out password hashes, MFA secrets, and sensitive authentication credentials.
    """
    auth_ctx.assert_active_company()
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)
    if not authorized_branches:
        return CompanyUsersPaginationResponse(items=[], total_count=0, total=0, page=page, page_size=page_size, total_pages=1)

    # If specific branch requested, it must be within authorized scope
    if branch_id is not None:
        if branch_id not in authorized_branches:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Branch #{branch_id} is outside your authorized branch scope.",
            )
        target_branches = {branch_id}
    else:
        target_branches = authorized_branches

    # Resolve user IDs matching target branch assignments
    assigned_user_ids = [
        r[0]
        for r in db.query(UserRoleAssignment.user_id)
        .filter(
            UserRoleAssignment.scope_type == "branch",
            UserRoleAssignment.scope_id.in_(target_branches),
        )
        .all()
    ]

    query = db.query(User).filter(
        User.company_id == auth_ctx.company_id,
        or_(
            User.branch_id.in_(target_branches),
            User.id.in_(assigned_user_ids) if assigned_user_ids else False,
        ),
    )

    if role:
        query = query.filter(User.role == role.strip().upper())

    if user_status:
        query = query.filter(User.status == user_status.strip().lower())

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

    company_branches = {
        b.id: b
        for b in db.query(Branch).filter(Branch.company_id == auth_ctx.company_id).all()
    }

    items = []
    for u in users:
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
                branch_code=primary_br.code if primary_br else "",
                assigned_branches=assigned_branches,
                mfa_enabled=mfa_enabled,
                created_at=u.created_at,
                must_change_password=u.must_change_password,
            )
        )

    return CompanyUsersPaginationResponse(
        items=items,
        total_count=total_count,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── 3. Invite Staff or Uploader ─────────────────────────────────────────────

@router.post("/users/invite", response_model=GenericMessageResponse)
@requires(USER_INVITE_BRANCH)
def invite_branch_user(
    payload: BranchUserInviteRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_INVITE_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    Invite a new STAFF or UPLOADER user strictly to an authorized branch.
    Prevents role escalation (cannot invite ADMIN or GLOBAL_ADMIN).
    Enforces tenant and branch isolation, user quotas, and audit logging.
    """
    auth_ctx.assert_active_company()

    # 1. Role validation & escalation prevention
    raw_role = payload.role.strip().upper()
    if raw_role in ("ADMIN", "GLOBAL_ADMIN", "MASTER_ADMIN", "ROOT") or "ADMIN" in raw_role:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Role escalation prohibited: Branch Admins can only invite Staff and Uploader users.",
        )

    valid_roles = {
        "STAFF": UserRole.STAFF,
        "UPLOADER": UserRole.UPLOADER,
    }
    if raw_role not in valid_roles:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{payload.role}'. Must be one of: {list(valid_roles.keys())}",
        )
    target_role = valid_roles[raw_role]

    # 2. Branch authorization check
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)
    target_branch_id = payload.branch_id if payload.branch_id is not None else auth_ctx.branch_id
    if target_branch_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Branch ID is required.",
        )

    if target_branch_id not in authorized_branches:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: You are not authorized to invite users into branch #{target_branch_id}.",
        )

    branch = (
        db.query(Branch)
        .filter(Branch.id == target_branch_id, Branch.company_id == auth_ctx.company_id)
        .first()
    )
    if not branch:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Selected branch does not belong to your company.",
        )

    if (branch.status or "active").lower() == "inactive":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Branch '{branch.name}' is inactive. Cannot invite users to an inactive branch.",
        )

    # 3. Quota enforcement with company row lock
    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Company not found.")

    active_count = db.query(func.count(User.id)).filter(
        User.company_id == company.id,
        User.status == AccountStatus.ACTIVE,
    ).scalar() or 0

    pending_inv = db.query(func.count(Invitation.id)).filter(
        Invitation.company_id == company.id,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    ).scalar() or 0

    if (active_count + pending_inv) >= company.max_users:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Company user limit reached: maximum {company.max_users} users allowed.",
        )

    # 4. Email uniqueness and existing user check
    normalized_email = payload.email.strip().lower()
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user and existing_user.status == AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"A user with email '{normalized_email}' is already active in the system.",
        )

    if not existing_user:
        placeholder_pwd = f"!invited_account_placeholder_{secrets.token_hex(32)}"
        new_user = User(
            company_id=company.id,
            branch_id=branch.id,
            name=payload.name.strip(),
            email=normalized_email,
            mobile=payload.mobile.strip() if payload.mobile else None,
            password_hash=placeholder_pwd,
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
        existing_user.branch_id = branch.id
        existing_user.name = payload.name.strip()
        existing_user.mobile = payload.mobile.strip() if payload.mobile else None
        existing_user.role = target_role
        existing_user.status = AccountStatus.INACTIVE
        new_user = existing_user

    # 5. Provision UserRoleAssignment records
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == new_user.id).delete(synchronize_session=False)
    db.add(
        UserRoleAssignment(
            user_id=new_user.id,
            role=raw_role,
            scope_type="branch",
            scope_id=branch.id,
            created_by=auth_ctx.user_id,
        )
    )
    if raw_role == "STAFF":
        db.add(
            UserRoleAssignment(
                user_id=new_user.id,
                role="UPLOADER",
                scope_type="branch",
                scope_id=branch.id,
                created_by=auth_ctx.user_id,
            )
        )

    # 6. Revoke prior invitations & generate token
    db.query(Invitation).filter(
        Invitation.email == normalized_email,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    ).update({"revoked_at": datetime.utcnow()}, synchronize_session=False)

    raw_token = secrets.token_hex(32)
    token_hash = hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)

    invitation = Invitation(
        email=normalized_email,
        company_id=company.id,
        branch_id=branch.id,
        invited_role=target_role,
        token_hash=token_hash,
        invited_by=auth_ctx.user_id,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    db.add(invitation)
    db.flush()

    # 7. Audit logging
    audit.record_event(
        db=db,
        action=USER_CREATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=new_user.id,
        metadata={"email": normalized_email, "role": raw_role, "branch_id": branch.id},
    )
    audit.record_event(
        db=db,
        action=AUTH_INVITATION_CREATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.INVITATION,
        object_id=invitation.id,
        metadata={"email": normalized_email, "role": raw_role, "branch_id": branch.id},
    )
    db.commit()

    activation_url = f"{settings.FRONTEND_URL.rstrip('/')}/accept-invite?token={raw_token}"
    try:
        email_service.send_invitation_email(
            to_email=normalized_email,
            company_name=company.name,
            branch_name=branch.name,
            role=raw_role,
            raw_token=raw_token,
        )
    except Exception as exc:
        logger.warning("Failed to dispatch branch invitation email: %s", exc)

    return GenericMessageResponse(
        message=f"Invitation successfully dispatched to '{normalized_email}'."
    )


# ── 4. Edit User Details ────────────────────────────────────────────────────

@router.put("/users/{user_id}", response_model=GenericMessageResponse)
@requires(USER_UPDATE_BRANCH)
def update_branch_user(
    user_id: int,
    payload: BranchUserUpdateRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_UPDATE_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    Update permitted details (name, email, mobile) of STAFF and UPLOADER accounts.
    Branch Admins cannot change roles, branch assignments, company IDs, or manage administrators.
    """
    auth_ctx.assert_active_company()

    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="User not found in your company.",
        )

    # 1. Branch boundary check
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)
    target_branches = get_target_user_branch_ids(target_user, db)
    if not target_branches.intersection(authorized_branches):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Target user does not belong to any of your authorized branches.",
        )

    # 2. Administrator immunity check: Branch Admin cannot modify Company Admin or Branch Admin
    if is_target_admin(target_user, db):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Branch Admins cannot modify administrator accounts.",
        )

    # 3. Apply profile updates
    changes: Dict[str, Any] = {}
    if payload.name is not None:
        name_val = payload.name.strip()
        if not name_val:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Name cannot be empty.")
        changes["old_name"] = target_user.name
        target_user.name = name_val
        changes["new_name"] = name_val

    if payload.mobile is not None:
        mob_val = payload.mobile.strip() or None
        target_user.mobile = mob_val
        changes["mobile"] = mob_val

    if payload.email is not None:
        email_val = payload.email.strip().lower()
        if not email_val:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Email cannot be empty.")
        if email_val != target_user.email:
            dup = db.query(User).filter(User.email == email_val, User.id != target_user.id).first()
            if dup:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Email '{email_val}' is already in use by another user.",
                )
            changes["old_email"] = target_user.email
            target_user.email = email_val
            changes["new_email"] = email_val

    audit.record_event(
        db=db,
        action=USER_UPDATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"branch_id": target_user.branch_id, "changes": changes},
    )
    db.commit()

    return GenericMessageResponse(message=f"User '{target_user.email}' updated successfully.")


# ── 5. Deactivate Branch User ───────────────────────────────────────────────

@router.post("/users/{user_id}/deactivate", response_model=GenericMessageResponse)
@requires(USER_DEACTIVATE_BRANCH)
def deactivate_branch_user(
    user_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_DEACTIVATE_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    Deactivate a STAFF or UPLOADER account within caller's authorized branches.
    Revokes all active sessions immediately and increments token_version.
    Does NOT delete historical user or document records.
    """
    auth_ctx.assert_active_company()

    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="User not found in your company.",
        )

    # Branch boundary check
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)
    target_branches = get_target_user_branch_ids(target_user, db)
    if not target_branches.intersection(authorized_branches):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Target user does not belong to any of your authorized branches.",
        )

    # Administrator immunity check
    if is_target_admin(target_user, db):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Branch Admins cannot deactivate administrator accounts.",
        )

    if target_user.status == AccountStatus.INACTIVE:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="User is already inactive.",
        )

    target_user.status = AccountStatus.INACTIVE

    # Immediately invalidate sessions and increment token_version
    session_service.revoke_all_sessions(
        db=db,
        identity_type="user",
        identity_id=target_user.id,
        reason="deactivated_by_branch_admin",
    )

    audit.record_event(
        db=db,
        action=USER_DEACTIVATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"email": target_user.email, "branch_id": target_user.branch_id},
    )
    db.commit()

    return GenericMessageResponse(message=f"User '{target_user.email}' has been deactivated and logged out.")


# ── 6. Reactivate Branch User ───────────────────────────────────────────────

@router.post("/users/{user_id}/activate", response_model=GenericMessageResponse)
@requires(USER_ACTIVATE_BRANCH)
def activate_branch_user(
    user_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_ACTIVATE_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    Reactivate an inactive STAFF or UPLOADER account within caller's authorized branches.
    Enforces company user quota.
    """
    auth_ctx.assert_active_company()

    company = db.query(Company).filter(Company.id == auth_ctx.company_id).with_for_update().first()
    if not company:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Company not found.")

    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == auth_ctx.company_id)
        .first()
    )
    if not target_user:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="User not found in your company.",
        )

    # Branch boundary check
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)
    target_branches = get_target_user_branch_ids(target_user, db)
    if not target_branches.intersection(authorized_branches):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Target user does not belong to any of your authorized branches.",
        )

    # Administrator immunity check
    if is_target_admin(target_user, db):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Branch Admins cannot activate administrator accounts.",
        )

    if target_user.status == AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="User is already active.",
        )

    # Check quota
    active_count = db.query(func.count(User.id)).filter(
        User.company_id == company.id,
        User.status == AccountStatus.ACTIVE,
    ).scalar() or 0

    if active_count >= company.max_users:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot activate user: company user limit of {company.max_users} has been reached.",
        )

    target_user.status = AccountStatus.ACTIVE

    audit.record_event(
        db=db,
        action=USER_REACTIVATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.USER,
        object_id=target_user.id,
        metadata={"email": target_user.email, "branch_id": target_user.branch_id},
    )
    db.commit()

    return GenericMessageResponse(message=f"User '{target_user.email}' has been reactivated successfully.")


# ── 7. Branch Invitations Management ────────────────────────────────────────

@router.get("/invitations", response_model=List[CompanyInvitationItem])
@requires(USER_VIEW_BRANCH)
def list_branch_invitations(
    branch_id: Optional[int] = Query(default=None),
    auth_ctx: AuthContext = Depends(require_permission(USER_VIEW_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    List pending and historical invitations within caller's authorized branches.
    """
    auth_ctx.assert_active_company()
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)
    if not authorized_branches:
        return []

    if branch_id is not None:
        if branch_id not in authorized_branches:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Branch #{branch_id} is outside your authorized scope.",
            )
        target_branches = {branch_id}
    else:
        target_branches = authorized_branches

    branches_map = {
        b.id: b
        for b in db.query(Branch).filter(Branch.company_id == auth_ctx.company_id).all()
    }
    inviters_map = {
        u.id: u.name
        for u in db.query(User).filter(User.company_id == auth_ctx.company_id).all()
    }

    invitations = (
        db.query(Invitation)
        .filter(
            Invitation.company_id == auth_ctx.company_id,
            Invitation.branch_id.in_(target_branches),
        )
        .order_by(Invitation.created_at.desc())
        .limit(100)
        .all()
    )

    now = datetime.utcnow()
    items = []
    for inv in invitations:
        is_accepted = inv.accepted_at is not None
        is_revoked = inv.revoked_at is not None
        is_expired = inv.expires_at < now and not is_accepted and not is_revoked
        is_valid = not is_accepted and not is_revoked and not is_expired

        if is_accepted:
            inv_status = "accepted"
        elif is_revoked:
            inv_status = "revoked"
        elif is_expired:
            inv_status = "expired"
        else:
            inv_status = "pending"

        br = branches_map.get(inv.branch_id)
        role_str = inv.invited_role.value if hasattr(inv.invited_role, "value") else str(inv.invited_role)

        items.append(
            CompanyInvitationItem(
                id=inv.id,
                email=inv.email,
                branch_id=inv.branch_id,
                branch_name=br.name if br else "Unknown",
                branch_code=br.code if br else "",
                invited_role=role_str,
                role=role_str,
                invited_by_name=inviters_map.get(inv.invited_by),
                expires_at=inv.expires_at,
                accepted_at=inv.accepted_at,
                revoked_at=inv.revoked_at,
                status=inv_status,
                accepted=is_accepted,
                revoked=is_revoked,
                is_valid=is_valid,
                created_at=inv.created_at,
            )
        )

    return items


@router.post("/invitations/{invitation_id}/resend", response_model=GenericMessageResponse)
@requires(USER_INVITE_BRANCH)
def resend_branch_invitation(
    invitation_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_INVITE_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    Resend an invitation with a fresh token within authorized branches.
    """
    auth_ctx.assert_active_company()
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)

    inv = (
        db.query(Invitation)
        .filter(Invitation.id == invitation_id, Invitation.company_id == auth_ctx.company_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

    if inv.branch_id not in authorized_branches:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Invitation branch is outside your authorized scope.",
        )

    # Disallow resending admin invitations by Branch Admin
    role_str = inv.invited_role.value if hasattr(inv.invited_role, "value") else str(inv.invited_role)
    if role_str in ("ADMIN", "GLOBAL_ADMIN") and not auth_ctx.is_global_admin:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Branch Admins cannot manage administrator invitations.",
        )

    if inv.accepted_at is not None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Cannot resend an invitation that has already been accepted.",
        )

    # Revoke old record & create fresh
    inv.revoked_at = datetime.utcnow()
    raw_token = secrets.token_hex(32)
    token_hash = hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)

    fresh_inv = Invitation(
        email=inv.email,
        company_id=inv.company_id,
        branch_id=inv.branch_id,
        invited_role=inv.invited_role,
        token_hash=token_hash,
        invited_by=auth_ctx.user_id,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    db.add(fresh_inv)
    db.flush()

    audit.record_event(
        db=db,
        action=AUTH_INVITATION_CREATE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.INVITATION,
        object_id=fresh_inv.id,
        metadata={"email": inv.email, "role": role_str, "branch_id": inv.branch_id, "action": "resend"},
    )
    db.commit()

    br = db.query(Branch).filter(Branch.id == inv.branch_id).first()
    branch_name = br.name if br else "Branch"
    activation_url = f"{settings.FRONTEND_URL.rstrip('/')}/accept-invite?token={raw_token}"
    try:
        email_service.send_invitation_email(
            to_email=inv.email,
            company_name=auth_ctx.company_name,
            branch_name=branch_name,
            role=role_str,
            raw_token=raw_token,
        )
    except Exception as exc:
        logger.warning("Failed to resend branch invitation email: %s", exc)

    return GenericMessageResponse(
        message=f"Invitation for '{inv.email}' resent successfully."
    )


@router.post("/invitations/{invitation_id}/revoke", response_model=GenericMessageResponse)
@requires(USER_INVITE_BRANCH)
def revoke_branch_invitation(
    invitation_id: int,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_INVITE_BRANCH)),
    db: Session = Depends(get_db),
):
    """
    Revoke a pending invitation within authorized branches.
    """
    auth_ctx.assert_active_company()
    authorized_branches = get_caller_authorized_branch_ids(auth_ctx, db)

    inv = (
        db.query(Invitation)
        .filter(Invitation.id == invitation_id, Invitation.company_id == auth_ctx.company_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

    if inv.branch_id not in authorized_branches:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Invitation branch is outside your authorized scope.",
        )

    role_str = inv.invited_role.value if hasattr(inv.invited_role, "value") else str(inv.invited_role)
    if role_str in ("ADMIN", "GLOBAL_ADMIN") and not auth_ctx.is_global_admin:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Branch Admins cannot manage administrator invitations.",
        )

    if inv.accepted_at is not None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke an already accepted invitation.",
        )

    if inv.revoked_at is not None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invitation is already revoked.",
        )

    inv.revoked_at = datetime.utcnow()
    audit.record_event(
        db=db,
        action=AUTH_INVITATION_REVOKE,
        request=request,
        auth_context=auth_ctx,
        object_type=ObjectType.INVITATION,
        object_id=inv.id,
        metadata={"email": inv.email, "branch_id": inv.branch_id},
    )
    db.commit()

    return GenericMessageResponse(message=f"Invitation for '{inv.email}' has been revoked.")
