"""
Centralized request authentication context (AuthContext) for DMS.

All tenant scoping, role evaluation, and company status validation are centralized here.
Endpoints receive a trusted AuthContext via FastAPI dependency injection.
Never trust client-supplied company_id or branch_id for tenant authorization.
"""

from dataclasses import dataclass, field
from typing import Optional, Sequence, Set, Union

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import decode_token, oauth2_scheme
from app.config import settings
from app.database import get_db
from app.models import (
    AccountStatus,
    Branch,
    Company,
    CompanyStatus,
    MasterAdmin,
    User,
    UserRole,
)


@dataclass(frozen=True)
class MasterAdminContext:
    """
    Context for platform-level Master Administrators.
    Strictly independent of tenant scoping.
    """
    admin_id: int
    admin_email: str
    admin_name: str
    status: AccountStatus
    token_version: int
    identity_type: str = "master_admin"


@dataclass(frozen=True)
class AuthContext:
    """
    Immutable, validated server-side authentication and tenant context.
    Derived strictly from the verified JWT and database user record.
    """
    user_id: int
    user_email: str
    user_name: str
    role: UserRole
    company_id: int
    company_name: str
    company_code: str
    company_status: CompanyStatus
    branch_id: int
    branch_name: str
    branch_code: str
    company_display_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    status: AccountStatus = AccountStatus.ACTIVE
    token_version: int = 1
    permissions: Set[str] = field(default_factory=set)
    assignments: tuple = field(default_factory=tuple)

    @property
    def is_global_admin(self) -> bool:
        return self.role == UserRole.GLOBAL_ADMIN

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.GLOBAL_ADMIN)

    @property
    def is_staff(self) -> bool:
        return self.role == UserRole.STAFF

    @property
    def is_active(self) -> bool:
        return self.company_status == CompanyStatus.ACTIVE and self.status == AccountStatus.ACTIVE

    @property
    def assigned_branch_ids(self) -> Set[int]:
        """
        Set of all branch IDs the user is authorized to access.
        For GLOBAL_ADMIN or users with company-wide document view, this is empty/None representing company-wide access.
        For branch-scoped roles, includes the primary branch_id plus any secondary branches
        from UserRoleAssignment records.
        """
        if self.is_global_admin or "document.view_company" in self.permissions:
            return set()
        branches = {self.branch_id}
        for a in self.assignments:
            if isinstance(a, dict) and a.get("scope_type") == "branch" and a.get("scope_id"):
                branches.add(int(a["scope_id"]))
        return branches

    def assert_active_company(self) -> None:
        """
        Enforce company suspension.
        Suspended company users (including GLOBAL_ADMIN) are strictly blocked with HTTP 403 Forbidden.
        Only Master Admins can inspect company metadata via platform routes.
        """
        if self.company_status == CompanyStatus.SUSPENDED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company account is suspended. Please contact your system administrator.",
            )


def _build_master_admin_context(
    token: str,
    db: Session,
    allow_unenrolled_mfa: bool = False,
) -> MasterAdminContext:
    """Validate platform JWT and return MasterAdminContext."""
    payload = decode_token(token, audience=settings.JWT_AUDIENCE_PLATFORM)

    # Reject restricted intermediate MFA tokens on standard platform routes
    token_type = payload.get("token_type")
    if token_type in ("mfa_pending", "mfa_enrollment_required"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication incomplete: Multi-factor authentication is required.",
        )

    admin_id = payload.get("master_admin_id")
    if not admin_id or payload.get("identity_type") != "master_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid platform token credentials",
        )

    admin = db.query(MasterAdmin).filter(MasterAdmin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator account not found",
        )

    if admin.status != AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator account is inactive or locked",
        )

    claim_tv = payload.get("token_version")
    if claim_tv is not None and claim_tv != admin.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked: please log in again",
        )

    if not allow_unenrolled_mfa:
        from app.services.mfa_service import MfaService
        if MfaService.is_mfa_mandatory_for_master_admin(db, admin) and not MfaService.is_mfa_enabled(db, "master_admin", admin.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Multi-factor authentication must be enrolled to access platform resources.",
            )

    return MasterAdminContext(
        admin_id=admin.id,
        admin_email=admin.email,
        admin_name=admin.name,
        status=admin.status,
        token_version=admin.token_version,
    )


def resolve_user_permissions_and_assignments(user: User, db: Session):
    """
    Resolves active roles, role assignments, and effective permissions for a user.
    """
    from app.models import UserRoleAssignment
    from app.auth.role_permissions import (
        get_effective_permissions,
        ROLE_GLOBAL_ADMIN,
        ROLE_ADMIN,
        ROLE_STAFF,
        ROLE_UPLOADER,
    )

    db_assignments = (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.user_id == user.id)
        .all()
    )

    roles = set()
    assignment_records = []
    if db_assignments:
        for a in db_assignments:
            roles.add(a.role)
            assignment_records.append({
                "id": a.id,
                "role": a.role,
                "scope_type": a.scope_type,
                "scope_id": a.scope_id,
            })
    else:
        # Fallback to legacy user.role if no explicit assignments yet
        if user.role:
            legacy_role = user.role.value if hasattr(user.role, "value") else str(user.role)
            roles.add(legacy_role)
            if legacy_role == "STAFF":
                roles.add(ROLE_UPLOADER)

    # ── Enforce Uploader Invariant ──────────────────────────────────────────
    # An Uploader must have one and only one branch assignment, no company assignment
    if ROLE_UPLOADER in roles or ROLE_STAFF in roles:
        uploader_assignments = [
            a for a in db_assignments if a.role in (ROLE_UPLOADER, ROLE_STAFF)
        ]
        if uploader_assignments:
            # 1. Reject any company-wide assignment for an Uploader
            if any(a.scope_type == "company" for a in uploader_assignments):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Integrity violation: Uploader cannot have company-wide assignment",
                )
            # 2. Reject assignments to multiple branches
            distinct_branches = {
                a.scope_id for a in uploader_assignments if a.scope_type == "branch"
            }
            if len(distinct_branches) > 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Integrity violation: Uploader cannot be assigned to multiple branches",
                )

    # Compute effective permissions from all active roles
    perms = get_effective_permissions(roles)

    # Legacy permission compatibility
    if user.role == UserRole.GLOBAL_ADMIN:
        perms.update({"all:read", "all:write", "all:delete", "company:manage"})
    elif user.role == UserRole.ADMIN:
        perms.update({"tenant:read", "tenant:write", "tenant:delete"})
    elif user.role == UserRole.STAFF:
        perms.update({"own:read", "own:write"})

    return perms, assignment_records


def _build_auth_context(
    token: str,
    db: Session,
    audience: Optional[Union[str, Sequence[str]]] = None,
    allow_suspended: bool = False,
    allow_unenrolled_mfa: bool = False,
) -> AuthContext:
    """
    Core token validation and AuthContext resolution.
    Validates JWT signature, expiry, audience, user record, account status,
    token version, company status, branch consistency, and mandatory MFA.
    """
    # If audience not specified, allow any valid tenant audience
    target_aud = audience or [
        settings.JWT_AUDIENCE_COMPANY,
        settings.JWT_AUDIENCE_APP,
        settings.JWT_AUDIENCE,
    ]
    payload = decode_token(token, audience=target_aud)

    # Reject restricted intermediate MFA tokens on standard data routes
    token_type = payload.get("token_type")
    if token_type in ("mfa_pending", "mfa_enrollment_required"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication incomplete: Multi-factor authentication is required.",
        )

    user_id = payload.get("user_id") or payload.get("uid")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user identity",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists",
        )

    # Validate active user status
    if user.status != AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive or locked",
        )

    # Validate token version
    claim_tv = payload.get("token_version")
    if claim_tv is not None and claim_tv != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked: please log in again",
        )

    # Validate company association
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User's assigned company not found",
        )

    # Validate branch association
    branch = db.query(Branch).filter(Branch.id == user.branch_id).first()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User's assigned branch not found",
        )

    # Enforce database relational integrity: branch MUST belong to user's company
    if branch.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Integrity violation: Branch does not belong to user's company",
        )

    # Enforce mandatory MFA
    if not allow_unenrolled_mfa:
        from app.services.mfa_service import MfaService
        if MfaService.is_mfa_mandatory_for_user(db, user) and not MfaService.is_mfa_enabled(db, "user", user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Multi-factor authentication must be enrolled to access company resources.",
            )

    # ── Resolve Module 4 Role Assignments & Effective Permissions ──────────
    perms, assignment_records = resolve_user_permissions_and_assignments(user, db)

    auth_ctx = AuthContext(
        user_id=user.id,
        user_email=user.email,
        user_name=user.name,
        role=user.role,
        company_id=company.id,
        company_name=company.name,
        company_display_name=company.display_name,
        company_logo_url=company.logo_url,
        company_code=company.code,
        company_status=company.status,
        branch_id=branch.id,
        branch_name=branch.name,
        branch_code=branch.code,
        status=user.status,
        token_version=user.token_version,
        permissions=perms,
        assignments=tuple(assignment_records),
    )

    if not allow_suspended:
        auth_ctx.assert_active_company()

    return auth_ctx



def get_auth_context(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    FastAPI dependency for standard Bearer token authorization.
    Automatically verifies active company status.
    """
    return _build_auth_context(token, db, allow_suspended=False)


def get_auth_context_from_query(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    FastAPI dependency that accepts token from Authorization header or ?token= query parameter.
    Used for direct file streaming endpoints (browser <img> / <iframe> / PDF views).
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _build_auth_context(token, db, allow_suspended=False)


def get_auth_context_allow_suspended(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    Dependency for administrative endpoints that need to inspect suspended companies.
    """
    return _build_auth_context(token, db, allow_suspended=True)


# ── Portal-Specific Dependencies ─────────────────────────────────────────────

def require_portal(portal: str, allow_unenrolled_mfa: bool = False):
    """
    Dependency factory enforcing portal-specific audience and identity rules:
      - 'platform': aud="platform", identity=MasterAdmin, status=ACTIVE
      - 'company': aud="company", identity=User with role=GLOBAL_ADMIN
      - 'app': aud="app", identity=User with role in (ADMIN, STAFF)
    """
    def portal_dependency(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db),
    ) -> Union[MasterAdminContext, AuthContext]:
        if portal == "platform":
            return _build_master_admin_context(token, db, allow_unenrolled_mfa=allow_unenrolled_mfa)
        elif portal == "company":
            ctx = _build_auth_context(token, db, audience=settings.JWT_AUDIENCE_COMPANY)
            if ctx.role != UserRole.GLOBAL_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Company Admin Portal access required.",
                )
            return ctx
        elif portal == "app":
            ctx = _build_auth_context(token, db, audience=settings.JWT_AUDIENCE_APP)
            if ctx.role not in (UserRole.ADMIN, UserRole.STAFF):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Branch Workspace access required.",
                )
            return ctx
        else:
            raise ValueError(f"Unknown portal: {portal}")

    return portal_dependency


require_platform = require_portal("platform", allow_unenrolled_mfa=True)
require_company = require_portal("company")
require_app = require_portal("app")

