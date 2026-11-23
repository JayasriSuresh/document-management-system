"""
Module 6 – Multi-Factor Authentication (MFA) Router.

Provides endpoints for:
  - MFA enrollment (start & verify with QR SVG and recovery codes)
  - MFA login verification (TOTP code & single-use recovery codes)
  - MFA status check
  - MFA disablement (with policy safeguards)
  - Recovery codes regeneration
  - Company & Platform MFA enforcement policies
  - Admin-assisted MFA resets
"""

import logging
import secrets
from datetime import datetime
from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, decode_token, verify_password
from app.auth.dependencies import require_permission
from app.auth.permissions import MFA_MANAGE_COMPANY, MFA_MANAGE_PLATFORM, MFA_MANAGE_BRANCH
from app.auth.role_permissions import ROLE_GLOBAL_ADMIN
from app.config import settings
from app.context import (
    AuthContext,
    MasterAdminContext,
    _build_auth_context,
    _build_master_admin_context,
    get_auth_context,
    require_company,
    require_platform,
    resolve_user_permissions_and_assignments,
)
from app.database import get_db
from app.models import (
    AccountStatus,
    Branch,
    Company,
    CompanyStatus,
    MasterAdmin,
    User,
    UserRole,
    UserRoleAssignment,
)
from app.schemas import (
    AdminMfaResetRequest,
    BranchMfaPolicyRequest,
    BranchMfaPolicyResponse,
    CompanyMfaPolicyRequest,
    CompanyMfaPolicyResponse,
    GenericMessageResponse,
    MasterAdminOut,
    MfaDisableRequest,
    MfaEnrollStartResponse,
    MfaEnrollVerifyRequest,
    MfaEnrollVerifyResponse,
    MfaRecoveryVerifyRequest,
    MfaRegenerateRecoveryRequest,
    MfaRegenerateRecoveryResponse,
    MfaStatusResponse,
    MfaVerifyRequest,
    PlatformMfaPolicyRequest,
    PlatformMfaPolicyResponse,
    TokenResponse,
    UserOut,
    UserRoleAssignmentOut,
)
from app.services.mfa_service import MfaService
from app.services.rate_limit_service import rate_limit_service
from app.services.session_service import session_service
from app.audit import (
    audit,
    ActorType,
    AUTH_LOGIN_SUCCESS,
    AUTH_MFA_ENROLL_START,
    AUTH_MFA_ENROLL_COMPLETE,
    AUTH_MFA_VERIFY_SUCCESS,
    AUTH_MFA_VERIFY_FAILURE,
    AUTH_MFA_RECOVERY_SUCCESS,
    AUTH_MFA_RECOVERY_FAILURE,
    AUTH_MFA_RECOVERY_REGENERATE,
    AUTH_MFA_DISABLE,
    AUTH_MFA_RESET_BY_ADMIN,
    AUTH_MFA_POLICY_UPDATE,
)

logger = logging.getLogger("dms.routers.mfa")

router = APIRouter(tags=["mfa"])


def _extract_token_from_request(
    request: Request, authorization: Optional[str] = None
) -> Optional[str]:
    """Extract Bearer token from header, parameter, or query param."""
    if authorization:
        if authorization.startswith("Bearer "):
            return authorization[7:].strip()
        return authorization.strip()
    header = request.headers.get("Authorization", "")
    if header:
        if header.startswith("Bearer "):
            return header[7:].strip()
        return header.strip()
    return request.query_params.get("token")


def _resolve_caller_identity(
    request: Request,
    db: Session,
    authorization: Optional[str] = None,
    allow_enrollment_token: bool = False,
) -> Dict[str, Any]:
    """
    Resolves the identity for MFA operations. Accepts:
      1. Standard Bearer token (MasterAdmin or User).
      2. If allow_enrollment_token=True, accepts mfa_enrollment_token.
    """
    token = _extract_token_from_request(request, authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(
            token,
            audience=[
                settings.JWT_AUDIENCE_PLATFORM,
                settings.JWT_AUDIENCE_COMPANY,
                settings.JWT_AUDIENCE_APP,
                settings.JWT_AUDIENCE,
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    t_type = payload.get("token_type")
    if t_type == "mfa_pending":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA pending token cannot perform enrollment.",
        )
    if t_type == "mfa_enrollment_required" and not allow_enrollment_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Full authentication required.",
        )

    aud = payload.get("aud")
    is_master = (aud == settings.JWT_AUDIENCE_PLATFORM) or (payload.get("identity_type") == "master_admin") or bool(payload.get("master_admin_id"))

    if is_master:
        admin_id = payload.get("master_admin_id")
        admin = db.query(MasterAdmin).filter_by(id=admin_id).first() if admin_id else None
        if not admin or admin.status != AccountStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid administrator identity.")

        return {
            "identity_type": "master_admin",
            "identity_id": admin.id,
            "email": admin.email,
            "role": "MASTER_ADMIN",
            "admin": admin,
            "user": None,
            "is_enrollment_token": (t_type == "mfa_enrollment_required"),
            "portal": "platform",
            "token": token,
        }
    else:
        user_id = payload.get("user_id") or payload.get("uid")
        user = db.query(User).filter_by(id=user_id).first() if user_id else None
        if not user or user.status != AccountStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity.")

        portal = "company" if user.role == UserRole.GLOBAL_ADMIN else "app"
        return {
            "identity_type": "user",
            "identity_id": user.id,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "admin": None,
            "user": user,
            "is_enrollment_token": (t_type == "mfa_enrollment_required"),
            "portal": portal,
            "token": token,
        }


def _resolve_user_effective_roles(user: User, db: Session) -> set[str]:
    from app.models import UserRoleAssignment
    roles = set()
    if user.role:
        roles.add(user.role.value if hasattr(user.role, "value") else str(user.role))
    db_assignments = (
        db.query(UserRoleAssignment.role)
        .filter(UserRoleAssignment.user_id == user.id)
        .all()
    )
    for (r,) in db_assignments:
        roles.add(r)
    return roles


# ── 1. ENROLLMENT ────────────────────────────────────────────────────────────

@router.post("/api/auth/mfa/enroll/start", response_model=MfaEnrollStartResponse)
def enroll_start(
    request: Request,
    regenerate: bool = Query(False),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Start MFA setup. Generates secret, stores encrypted pending secret,
    and returns QR code SVG + manual entry secret key.
    Accepts full access token or mfa_enrollment_token.
    """
    ident = _resolve_caller_identity(request, db, authorization, allow_enrollment_token=True)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    # If calling with a full session token (not an enrollment_token), check if voluntary self-enrollment is permitted
    if not ident.get("is_enrollment_token") and ident["identity_type"] == "user":
        target_u = ident["user"]
        target_roles = _resolve_user_effective_roles(target_u, db)
        # Voluntary opt-in is reserved for administrators (GLOBAL_ADMIN, ADMIN); Staff and Uploader cannot voluntarily enroll when optional
        if "GLOBAL_ADMIN" not in target_roles and "ADMIN" not in target_roles and not MfaService.is_mfa_mandatory_for_user(db, target_u):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Individual self-enrollment is disabled for your role. Contact your administrator.",
            )

    result = MfaService.start_enrollment(
        db=db,
        identity_type=ident["identity_type"],
        identity_id=ident["identity_id"],
        account_name=ident["email"],
        force_regenerate=regenerate,
    )

    actor_type = ActorType.MASTER_ADMIN if ident["identity_type"] == "master_admin" else ActorType.COMPANY_USER
    company_id = getattr(ident["user"], "company_id", None) if ident["user"] else None
    branch_id = getattr(ident["user"], "branch_id", None) if ident["user"] else None

    audit.record(
        db=db,
        action=AUTH_MFA_ENROLL_START,
        actor_type=actor_type,
        actor_id=ident["identity_id"],
        company_id=company_id,
        branch_id=branch_id,
        object_type="mfa",
        object_id=str(ident["identity_id"]),
        ip=client_ip,
        user_agent=user_agent,
        metadata={"email": ident["email"]},
    )
    db.commit()

    return MfaEnrollStartResponse(
        secret=result["secret"],
        provisioning_uri=result["provisioning_uri"],
        qr_code_svg=result["qr_code_svg"],
        qr_code_data_url=result.get("qr_code_data_url"),
    )


@router.post("/api/auth/mfa/enroll/verify", response_model=MfaEnrollVerifyResponse)
def enroll_verify(
    payload: MfaEnrollVerifyRequest,
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Verify TOTP code and finalize MFA activation.
    Generates 8 single-use recovery codes.
    If completing mandatory enrollment, finalizes authentication and issues full session/tokens.
    """
    token_str = payload.enrollment_token or authorization
    ident = _resolve_caller_identity(request, db, token_str, allow_enrollment_token=True)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    recovery_codes = MfaService.verify_and_enable(
        db=db,
        identity_type=ident["identity_type"],
        identity_id=ident["identity_id"],
        code=payload.code,
    )

    actor_type = ActorType.MASTER_ADMIN if ident["identity_type"] == "master_admin" else ActorType.COMPANY_USER
    company_id = getattr(ident["user"], "company_id", None) if ident["user"] else None
    branch_id = getattr(ident["user"], "branch_id", None) if ident["user"] else None

    audit.record(
        db=db,
        action=AUTH_MFA_ENROLL_COMPLETE,
        actor_type=actor_type,
        actor_id=ident["identity_id"],
        company_id=company_id,
        branch_id=branch_id,
        object_type="mfa",
        object_id=str(ident["identity_id"]),
        ip=client_ip,
        user_agent=user_agent,
        metadata={"email": ident["email"], "remaining_recovery_codes": len(recovery_codes)},
    )

    access_token = None
    user_out = None

    # If this was completing a mandatory enrollment during login, finalize login
    if ident["is_enrollment_token"]:
        session, raw_refresh = session_service.create_session(
            db=db,
            identity_type=ident["identity_type"],
            identity_id=ident["identity_id"],
            user_agent=user_agent,
            ip_address=client_ip,
        )

        response.set_cookie(
            key="dms_refresh_token",
            value=raw_refresh,
            httponly=True,
            secure=settings.is_cookie_secure,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/",
        )

        if ident["identity_type"] == "master_admin":
            admin = ident["admin"]
            rate_limit_service.record_successful_login(db, admin)
            claims = {
                "sub": admin.email,
                "master_admin_id": admin.id,
                "identity_type": "master_admin",
                "role": "MASTER_ADMIN",
                "token_version": admin.token_version,
                "jti": secrets.token_hex(16),
            }
            access_token = create_access_token(data=claims, audience=settings.JWT_AUDIENCE_PLATFORM)
            user_out = MasterAdminOut(
                id=admin.id,
                name=admin.name,
                email=admin.email,
                role="MASTER_ADMIN",
                portal="platform",
                status=admin.status.value,
            )
            audit.record(
                db=db,
                action=AUTH_LOGIN_SUCCESS,
                actor_type=ActorType.MASTER_ADMIN,
                actor_id=admin.id,
                object_type="master_admin",
                object_id=str(admin.id),
                ip=client_ip,
                user_agent=user_agent,
                metadata={"email": admin.email, "portal": "platform", "mfa_method": "totp"},
            )
        else:
            user = ident["user"]
            rate_limit_service.record_successful_login(db, user)
            target_aud = (
                settings.JWT_AUDIENCE_COMPANY
                if user.role == UserRole.GLOBAL_ADMIN
                else settings.JWT_AUDIENCE_APP
            )
            claims = {
                "sub": user.email,
                "uid": user.id,
                "user_id": user.id,
                "company_id": user.company_id,
                "branch_id": user.branch_id,
                "tenant_id": user.branch_id,
                "role": user.role.value,
                "identity_type": "user",
                "token_version": user.token_version,
                "jti": secrets.token_hex(16),
            }
            access_token = create_access_token(data=claims, audience=target_aud)
            user_out = UserOut(
                id=user.id,
                name=user.name,
                email=user.email,
                role=user.role,
                company_id=user.company_id,
                company_name=user.company.name if user.company else "",
                branch_id=user.branch_id,
                branch_name=user.branch.name if user.branch else "",
                branch_code=user.branch.code if user.branch else "",
                tenant_id=user.branch_id,
                tenant_name=user.branch.name if user.branch else "",
            )
            audit.record(
                db=db,
                action=AUTH_LOGIN_SUCCESS,
                actor_type=ActorType.COMPANY_USER,
                actor_id=user.id,
                company_id=user.company_id,
                branch_id=user.branch_id,
                object_type="user",
                object_id=str(user.id),
                ip=client_ip,
                user_agent=user_agent,
                metadata={"email": user.email, "portal": ident["portal"], "mfa_method": "totp"},
            )

    db.commit()

    return MfaEnrollVerifyResponse(
        message="MFA enabled successfully. Please store your recovery codes in a safe place.",
        recovery_codes=recovery_codes,
        access_token=access_token,
        portal=ident["portal"] if ident["is_enrollment_token"] else None,
        user=user_out,
    )


# ── 2. LOGIN VERIFICATION (TOTP & RECOVERY) ──────────────────────────────────

def _decode_mfa_pending_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a restricted mfa_pending token."""
    audiences = [
        settings.JWT_AUDIENCE_PLATFORM,
        settings.JWT_AUDIENCE_COMPANY,
        settings.JWT_AUDIENCE_APP,
        settings.JWT_AUDIENCE,
    ]
    try:
        payload = decode_token(token, audience=audiences)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired MFA token: {e}",
        )

    if payload.get("token_type") != "mfa_pending":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not an MFA challenge token.",
        )

    return payload


@router.post("/api/auth/mfa/verify", response_model=TokenResponse)
def verify_totp(
    payload: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Step 2 of login: verify 6-digit TOTP code against restricted mfa_pending_token.
    Enforces replay protection and account lockout on failure.
    """
    token_claims = _decode_mfa_pending_token(payload.code if not payload.mfa_pending_token else payload.mfa_pending_token)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    identity_type = token_claims.get("identity_type", "user")
    if identity_type == "master_admin":
        admin_id = token_claims.get("master_admin_id")
        admin = db.query(MasterAdmin).filter_by(id=admin_id).first()
        if not admin:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin account not found.")

        rate_limit_service.check_lockout(admin)

        success, err = MfaService.verify_totp_code(db, "master_admin", admin.id, payload.code)
        if not success:
            rate_limit_service.record_failed_attempt(db, admin)
            audit.record_auth_failure(
                action=AUTH_MFA_VERIFY_FAILURE,
                email=admin.email,
                reason=err or "Invalid verification code",
                request=request,
                actor_type=ActorType.MASTER_ADMIN,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err or "Invalid authentication code.")

        # Successful MFA login
        rate_limit_service.record_successful_login(db, admin)
        session, raw_refresh = session_service.create_session(
            db=db,
            identity_type="master_admin",
            identity_id=admin.id,
            user_agent=user_agent,
            ip_address=client_ip,
        )

        response.set_cookie(
            key="dms_refresh_token",
            value=raw_refresh,
            httponly=True,
            secure=settings.is_cookie_secure,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/",
        )

        claims = {
            "sub": admin.email,
            "master_admin_id": admin.id,
            "identity_type": "master_admin",
            "role": "MASTER_ADMIN",
            "token_version": admin.token_version,
            "jti": secrets.token_hex(16),
        }
        access_token = create_access_token(data=claims, audience=settings.JWT_AUDIENCE_PLATFORM)

        user_out = MasterAdminOut(
            id=admin.id,
            name=admin.name,
            email=admin.email,
            role="MASTER_ADMIN",
            portal="platform",
            status=admin.status.value,
        )

        audit.record(
            db=db,
            action=AUTH_MFA_VERIFY_SUCCESS,
            actor_type=ActorType.MASTER_ADMIN,
            actor_id=admin.id,
            object_type="master_admin",
            object_id=str(admin.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": admin.email, "portal": "platform", "mfa_method": "totp"},
        )
        audit.record(
            db=db,
            action=AUTH_LOGIN_SUCCESS,
            actor_type=ActorType.MASTER_ADMIN,
            actor_id=admin.id,
            object_type="master_admin",
            object_id=str(admin.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": admin.email, "portal": "platform", "mfa_method": "totp"},
        )
        db.commit()

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            portal="platform",
            must_change_password=admin.must_change_password,
            user=user_out,
        )

    else:
        # Tenant user
        user_id = token_claims.get("user_id") or token_claims.get("uid")
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found.")

        rate_limit_service.check_lockout(user)

        success, err = MfaService.verify_totp_code(db, "user", user.id, payload.code)
        if not success:
            rate_limit_service.record_failed_attempt(db, user)
            audit.record_auth_failure(
                action=AUTH_MFA_VERIFY_FAILURE,
                email=user.email,
                reason=err or "Invalid verification code",
                request=request,
                actor_type=ActorType.COMPANY_USER,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err or "Invalid authentication code.")

        # Successful MFA login
        rate_limit_service.record_successful_login(db, user)
        session, raw_refresh = session_service.create_session(
            db=db,
            identity_type="user",
            identity_id=user.id,
            user_agent=user_agent,
            ip_address=client_ip,
        )

        response.set_cookie(
            key="dms_refresh_token",
            value=raw_refresh,
            httponly=True,
            secure=settings.is_cookie_secure,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/",
        )

        portal = "company" if user.role == UserRole.GLOBAL_ADMIN else "app"
        target_aud = (
            settings.JWT_AUDIENCE_COMPANY
            if user.role == UserRole.GLOBAL_ADMIN
            else settings.JWT_AUDIENCE_APP
        )

        claims = {
            "sub": user.email,
            "uid": user.id,
            "user_id": user.id,
            "company_id": user.company_id,
            "branch_id": user.branch_id,
            "tenant_id": user.branch_id,
            "role": user.role.value,
            "identity_type": "user",
            "token_version": user.token_version,
            "jti": secrets.token_hex(16),
        }
        access_token = create_access_token(data=claims, audience=target_aud)

        from app.context import resolve_user_permissions_and_assignments
        perms, assignments = resolve_user_permissions_and_assignments(user, db)

        user_out = UserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            company_id=user.company_id,
            company_name=user.company.name if user.company else "",
            branch_id=user.branch_id,
            branch_name=user.branch.name if user.branch else "",
            branch_code=user.branch.code if user.branch else "",
            permissions=sorted(list(perms)),
            assignments=[UserRoleAssignmentOut(**a) for a in assignments],
            tenant_id=user.branch_id,
            tenant_name=user.branch.name if user.branch else "",
        )

        audit.record(
            db=db,
            action=AUTH_MFA_VERIFY_SUCCESS,
            actor_type=ActorType.COMPANY_USER,
            actor_id=user.id,
            company_id=user.company_id,
            branch_id=user.branch_id,
            object_type="user",
            object_id=str(user.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": user.email, "portal": portal, "mfa_method": "totp"},
        )
        audit.record(
            db=db,
            action=AUTH_LOGIN_SUCCESS,
            actor_type=ActorType.COMPANY_USER,
            actor_id=user.id,
            company_id=user.company_id,
            branch_id=user.branch_id,
            object_type="user",
            object_id=str(user.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": user.email, "portal": portal, "mfa_method": "totp"},
        )
        db.commit()

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            portal=portal,
            must_change_password=user.must_change_password,
            user=user_out,
        )


@router.post("/api/auth/mfa/recovery/verify", response_model=TokenResponse)
def verify_recovery(
    payload: MfaRecoveryVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Step 2 fallback: redeem a single-use recovery code against restricted mfa_pending_token.
    Code is checked, row-locked, and atomically marked as used.
    """
    token_claims = _decode_mfa_pending_token(payload.mfa_pending_token)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    identity_type = token_claims.get("identity_type", "user")
    if identity_type == "master_admin":
        admin_id = token_claims.get("master_admin_id")
        admin = db.query(MasterAdmin).filter_by(id=admin_id).first()
        if not admin:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin account not found.")

        rate_limit_service.check_lockout(admin)

        success, err = MfaService.verify_recovery_code(db, "master_admin", admin.id, payload.recovery_code)
        if not success:
            rate_limit_service.record_failed_attempt(db, admin)
            audit.record_auth_failure(
                action=AUTH_MFA_RECOVERY_FAILURE,
                email=admin.email,
                reason=err or "Invalid recovery code",
                request=request,
                actor_type=ActorType.MASTER_ADMIN,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err or "Invalid recovery code.")

        rate_limit_service.record_successful_login(db, admin)
        session, raw_refresh = session_service.create_session(
            db=db,
            identity_type="master_admin",
            identity_id=admin.id,
            user_agent=user_agent,
            ip_address=client_ip,
        )

        response.set_cookie(
            key="dms_refresh_token",
            value=raw_refresh,
            httponly=True,
            secure=settings.is_cookie_secure,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/",
        )

        claims = {
            "sub": admin.email,
            "master_admin_id": admin.id,
            "identity_type": "master_admin",
            "role": "MASTER_ADMIN",
            "token_version": admin.token_version,
            "jti": secrets.token_hex(16),
        }
        access_token = create_access_token(data=claims, audience=settings.JWT_AUDIENCE_PLATFORM)

        user_out = MasterAdminOut(
            id=admin.id,
            name=admin.name,
            email=admin.email,
            role="MASTER_ADMIN",
            portal="platform",
            status=admin.status.value,
        )

        audit.record(
            db=db,
            action=AUTH_MFA_RECOVERY_SUCCESS,
            actor_type=ActorType.MASTER_ADMIN,
            actor_id=admin.id,
            object_type="master_admin",
            object_id=str(admin.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": admin.email, "portal": "platform", "mfa_method": "recovery_code"},
        )
        audit.record(
            db=db,
            action=AUTH_LOGIN_SUCCESS,
            actor_type=ActorType.MASTER_ADMIN,
            actor_id=admin.id,
            object_type="master_admin",
            object_id=str(admin.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": admin.email, "portal": "platform", "mfa_method": "recovery_code"},
        )
        db.commit()

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            portal="platform",
            must_change_password=admin.must_change_password,
            user=user_out,
        )

    else:
        user_id = token_claims.get("user_id") or token_claims.get("uid")
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found.")

        rate_limit_service.check_lockout(user)

        success, err = MfaService.verify_recovery_code(db, "user", user.id, payload.recovery_code)
        if not success:
            rate_limit_service.record_failed_attempt(db, user)
            audit.record_auth_failure(
                action=AUTH_MFA_RECOVERY_FAILURE,
                email=user.email,
                reason=err or "Invalid recovery code",
                request=request,
                actor_type=ActorType.COMPANY_USER,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err or "Invalid recovery code.")

        rate_limit_service.record_successful_login(db, user)
        session, raw_refresh = session_service.create_session(
            db=db,
            identity_type="user",
            identity_id=user.id,
            user_agent=user_agent,
            ip_address=client_ip,
        )

        response.set_cookie(
            key="dms_refresh_token",
            value=raw_refresh,
            httponly=True,
            secure=settings.is_cookie_secure,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/",
        )

        portal = "company" if user.role == UserRole.GLOBAL_ADMIN else "app"
        target_aud = (
            settings.JWT_AUDIENCE_COMPANY
            if user.role == UserRole.GLOBAL_ADMIN
            else settings.JWT_AUDIENCE_APP
        )

        claims = {
            "sub": user.email,
            "uid": user.id,
            "user_id": user.id,
            "company_id": user.company_id,
            "branch_id": user.branch_id,
            "tenant_id": user.branch_id,
            "role": user.role.value,
            "identity_type": "user",
            "token_version": user.token_version,
            "jti": secrets.token_hex(16),
        }
        access_token = create_access_token(data=claims, audience=target_aud)

        from app.context import resolve_user_permissions_and_assignments
        perms, assignments = resolve_user_permissions_and_assignments(user, db)

        user_out = UserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            company_id=user.company_id,
            company_name=user.company.name if user.company else "",
            branch_id=user.branch_id,
            branch_name=user.branch.name if user.branch else "",
            branch_code=user.branch.code if user.branch else "",
            permissions=sorted(list(perms)),
            assignments=[UserRoleAssignmentOut(**a) for a in assignments],
            tenant_id=user.branch_id,
            tenant_name=user.branch.name if user.branch else "",
        )

        audit.record(
            db=db,
            action=AUTH_MFA_RECOVERY_SUCCESS,
            actor_type=ActorType.COMPANY_USER,
            actor_id=user.id,
            company_id=user.company_id,
            branch_id=user.branch_id,
            object_type="user",
            object_id=str(user.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": user.email, "portal": portal, "mfa_method": "recovery_code"},
        )
        audit.record(
            db=db,
            action=AUTH_LOGIN_SUCCESS,
            actor_type=ActorType.COMPANY_USER,
            actor_id=user.id,
            company_id=user.company_id,
            branch_id=user.branch_id,
            object_type="user",
            object_id=str(user.id),
            ip=client_ip,
            user_agent=user_agent,
            metadata={"email": user.email, "portal": portal, "mfa_method": "recovery_code"},
        )
        db.commit()

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            portal=portal,
            must_change_password=user.must_change_password,
            user=user_out,
        )


# ── 3. STATUS, DISABLE & RECOVERY REGENERATE ─────────────────────────────────

@router.get("/api/auth/mfa/status", response_model=MfaStatusResponse)
def get_status(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Returns current user/admin MFA status, remaining recovery codes, and mandatory policy."""
    ident = _resolve_caller_identity(request, db, authorization, allow_enrollment_token=True)
    status_dict = MfaService.get_mfa_status(db, ident["identity_type"], ident["identity_id"])
    return MfaStatusResponse(**status_dict)


@router.post("/api/auth/mfa/disable", response_model=GenericMessageResponse)
def disable_mfa(
    payload: MfaDisableRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Disable MFA. Requires password and TOTP code.
    Blocked if MFA is mandated by company or platform policy.
    Restricted to administrators; Staff and Uploaders cannot self-disable.
    """
    ident = _resolve_caller_identity(request, db, authorization, allow_enrollment_token=False)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    # Staff and Uploader accounts cannot disable MFA
    if ident["identity_type"] == "user":
        target_u = ident["user"]
        target_roles = _resolve_user_effective_roles(target_u, db)
        if "GLOBAL_ADMIN" not in target_roles and "ADMIN" not in target_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to disable MFA. Contact your administrator.",
            )

    # Verify password
    pwd_hash = ident["admin"].password_hash if ident["identity_type"] == "master_admin" else ident["user"].password_hash
    if not verify_password(payload.password, pwd_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password.",
        )

    # Verify TOTP code
    success, err = MfaService.verify_totp_code(db, ident["identity_type"], ident["identity_id"], payload.code)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err or "Invalid authentication code.",
        )

    # Disables MFA (raises 403 if mandatory)
    MfaService.disable_mfa(db, ident["identity_type"], ident["identity_id"])

    actor_type = ActorType.MASTER_ADMIN if ident["identity_type"] == "master_admin" else ActorType.COMPANY_USER
    company_id = getattr(ident["user"], "company_id", None) if ident["user"] else None
    branch_id = getattr(ident["user"], "branch_id", None) if ident["user"] else None

    audit.record(
        db=db,
        action=AUTH_MFA_DISABLE,
        actor_type=actor_type,
        actor_id=ident["identity_id"],
        company_id=company_id,
        branch_id=branch_id,
        object_type="mfa",
        object_id=str(ident["identity_id"]),
        ip=client_ip,
        user_agent=user_agent,
        metadata={"email": ident["email"]},
    )
    db.commit()

    return GenericMessageResponse(message="MFA has been successfully disabled.")


@router.post("/api/auth/mfa/recovery/regenerate", response_model=MfaRegenerateRecoveryResponse)
def regenerate_recovery(
    payload: MfaRegenerateRecoveryRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Regenerates recovery codes. Requires active MFA.
    Validates password or TOTP code.
    Restricted to administrators (Master Admin, Company Admin, Branch Admin).
    """
    ident = _resolve_caller_identity(request, db, authorization, allow_enrollment_token=False)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    # Non-administrative users (Staff, Uploader) cannot regenerate recovery codes
    if ident["identity_type"] == "user":
        target_u = ident["user"]
        target_roles = _resolve_user_effective_roles(target_u, db)
        if "GLOBAL_ADMIN" not in target_roles and "ADMIN" not in target_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Recovery-code regeneration is restricted to administrators. Contact your administrator.",
            )

    if payload.code:
        success, err = MfaService.verify_totp_code(db, ident["identity_type"], ident["identity_id"], payload.code)
        if not success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err or "Invalid verification code.")
    elif payload.password:
        pwd_hash = ident["admin"].password_hash if ident["identity_type"] == "master_admin" else ident["user"].password_hash
        if not verify_password(payload.password, pwd_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password.")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code or password is required to regenerate recovery codes.",
        )

    new_codes = MfaService.regenerate_recovery_codes(db, ident["identity_type"], ident["identity_id"])

    actor_type = ActorType.MASTER_ADMIN if ident["identity_type"] == "master_admin" else ActorType.COMPANY_USER
    company_id = getattr(ident["user"], "company_id", None) if ident["user"] else None
    branch_id = getattr(ident["user"], "branch_id", None) if ident["user"] else None

    audit.record(
        db=db,
        action=AUTH_MFA_RECOVERY_REGENERATE,
        actor_type=actor_type,
        actor_id=ident["identity_id"],
        company_id=company_id,
        branch_id=branch_id,
        object_type="mfa",
        object_id=str(ident["identity_id"]),
        ip=client_ip,
        user_agent=user_agent,
        metadata={"email": ident["email"], "remaining_recovery_codes": len(new_codes)},
    )
    db.commit()

    return MfaRegenerateRecoveryResponse(
        message="New recovery codes generated. All previous recovery codes have been invalidated.",
        recovery_codes=new_codes,
    )


# ── 4. COMPANY, BRANCH & PLATFORM MFA POLICIES ────────────────────────────────

@router.get(
    "/api/company/security/mfa-policy",
    response_model=CompanyMfaPolicyResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_COMPANY))],
)
def get_company_mfa_policy(
    auth_ctx: AuthContext = Depends(require_company),
    db: Session = Depends(get_db),
):
    """Fetch company MFA policy and delegation settings (Company Admin only)."""
    company = db.query(Company).filter_by(id=auth_ctx.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    return CompanyMfaPolicyResponse(
        company_id=company.id,
        mfa_required_for_all=bool(company.mfa_required_for_all),
        allow_branch_mfa_control=bool(getattr(company, "allow_branch_mfa_control", False)),
    )


@router.post(
    "/api/company/security/mfa-policy",
    response_model=CompanyMfaPolicyResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_COMPANY))],
)
def update_company_mfa_policy(
    payload: CompanyMfaPolicyRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(require_company),
    db: Session = Depends(get_db),
):
    """Update company MFA policy and branch delegation (Company Admin only)."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    company = db.query(Company).filter_by(id=auth_ctx.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    platform_policy = MfaService.get_platform_mfa_policy(db)
    # Anti-downgrade check against platform enforce_all
    if platform_policy.get("enforce_all") and payload.mfa_required_for_all is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is enforced platform-wide by Master Administration and cannot be relaxed.",
        )

    prev_mfa_required = bool(company.mfa_required_for_all)
    if payload.mfa_required_for_all is not None:
        company.mfa_required_for_all = payload.mfa_required_for_all
    if payload.allow_branch_mfa_control is not None:
        company.allow_branch_mfa_control = payload.allow_branch_mfa_control
    company.updated_at = datetime.utcnow()

    # If transitioned from optional to mandatory, invalidate active sessions across all company users
    if not prev_mfa_required and company.mfa_required_for_all:
        affected_user_ids = [row[0] for row in db.query(User.id).filter(User.company_id == company.id).all()]
        MfaService.invalidate_sessions_for_users(db, affected_user_ids, reason="company_mfa_policy_mandated")

    audit.record(
        db=db,
        action=AUTH_MFA_POLICY_UPDATE,
        actor_type=ActorType.COMPANY_USER,
        actor_id=auth_ctx.user_id,
        company_id=auth_ctx.company_id,
        branch_id=auth_ctx.branch_id,
        object_type="security_policy",
        object_id=str(company.id),
        ip=client_ip,
        user_agent=user_agent,
        metadata={
            "mfa_required_for_all": company.mfa_required_for_all,
            "allow_branch_mfa_control": getattr(company, "allow_branch_mfa_control", False),
        },
    )
    db.commit()

    return CompanyMfaPolicyResponse(
        company_id=company.id,
        mfa_required_for_all=company.mfa_required_for_all,
        allow_branch_mfa_control=bool(getattr(company, "allow_branch_mfa_control", False)),
    )


# ── BRANCH MFA POLICY ENDPOINTS ──────────────────────────────────────────────

@router.get(
    "/api/branch/{branch_id}/security/mfa-policy",
    response_model=BranchMfaPolicyResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_BRANCH))],
)
def get_branch_mfa_policy(
    branch_id: int,
    auth_ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Fetch branch MFA policy and effective lock state."""
    branch = db.query(Branch).filter_by(id=branch_id, company_id=auth_ctx.company_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

    if not auth_ctx.is_global_admin and branch.id not in auth_ctx.assigned_branch_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: Branch outside assigned scope.")

    platform_policy = MfaService.get_platform_mfa_policy(db)
    company = db.query(Company).filter_by(id=auth_ctx.company_id).first()

    is_locked = False
    lock_reason = None
    if platform_policy.get("enforce_all"):
        is_locked = True
        lock_reason = "Platform policy mandates MFA for all users."
    elif company and company.mfa_required_for_all:
        is_locked = True
        lock_reason = "Company policy mandates MFA for all users."

    effective_mfa = is_locked or bool(getattr(branch, "mfa_required_for_all", False))

    return BranchMfaPolicyResponse(
        branch_id=branch.id,
        company_id=branch.company_id,
        mfa_required_for_all=bool(getattr(branch, "mfa_required_for_all", False)),
        effective_mfa_required=effective_mfa,
        is_locked_by_higher_policy=is_locked,
        lock_reason=lock_reason,
    )


@router.post(
    "/api/branch/{branch_id}/security/mfa-policy",
    response_model=BranchMfaPolicyResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_BRANCH))],
)
def update_branch_mfa_policy(
    branch_id: int,
    payload: BranchMfaPolicyRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Update branch-specific MFA policy (Delegated Branch Admin or Company Admin)."""
    branch = db.query(Branch).filter_by(id=branch_id, company_id=auth_ctx.company_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found.")

    if not auth_ctx.is_global_admin and branch.id not in auth_ctx.assigned_branch_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: Branch outside assigned scope.")

    platform_policy = MfaService.get_platform_mfa_policy(db)
    company = db.query(Company).filter_by(id=auth_ctx.company_id).first()

    # Anti-downgrade 1: Platform enforce_all
    if platform_policy.get("enforce_all") and payload.mfa_required_for_all is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is enforced platform-wide by Master Administration and cannot be modified at the branch level.",
        )

    # Anti-downgrade 2: Company mfa_required_for_all
    if company and company.mfa_required_for_all and payload.mfa_required_for_all is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is mandated company-wide by your Company Administrator and cannot be weakened for this branch.",
        )

    # Delegation check: if caller is not GLOBAL_ADMIN, company must have allow_branch_mfa_control enabled
    if not auth_ctx.is_global_admin and not getattr(company, "allow_branch_mfa_control", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Branch-level MFA policy management has not been delegated by your Company Administrator.",
        )

    prev_mfa_required = bool(getattr(branch, "mfa_required_for_all", False))
    branch.mfa_required_for_all = payload.mfa_required_for_all
    branch.updated_at = datetime.utcnow()

    # Invalidate sessions for affected branch users if transitioned to mandatory
    if not prev_mfa_required and branch.mfa_required_for_all:
        from sqlalchemy import or_, and_
        branch_user_ids = [
            row[0] for row in db.query(User.id)
            .outerjoin(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .filter(
                User.company_id == auth_ctx.company_id,
                or_(
                    User.branch_id == branch.id,
                    and_(UserRoleAssignment.scope_type == "branch", UserRoleAssignment.scope_id == branch.id),
                ),
            )
            .distinct()
            .all()
        ]
        MfaService.invalidate_sessions_for_users(db, branch_user_ids, reason="branch_mfa_policy_mandated")

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    audit.record(
        db=db,
        action=AUTH_MFA_POLICY_UPDATE,
        actor_type=ActorType.COMPANY_USER,
        actor_id=auth_ctx.user_id,
        company_id=auth_ctx.company_id,
        branch_id=branch.id,
        object_type="security_policy",
        object_id=f"branch_{branch.id}",
        ip=client_ip,
        user_agent=user_agent,
        metadata={"mfa_required_for_all": branch.mfa_required_for_all},
    )
    db.commit()

    is_locked = bool(platform_policy.get("enforce_all") or (company and company.mfa_required_for_all))
    effective_mfa = is_locked or bool(branch.mfa_required_for_all)

    return BranchMfaPolicyResponse(
        branch_id=branch.id,
        company_id=branch.company_id,
        mfa_required_for_all=branch.mfa_required_for_all,
        effective_mfa_required=effective_mfa,
        is_locked_by_higher_policy=is_locked,
        lock_reason="Platform or company policy enforces MFA." if is_locked else None,
    )


@router.get(
    "/api/admin/security/mfa-policy",
    response_model=PlatformMfaPolicyResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_PLATFORM))],
)
def get_platform_mfa_policy(
    admin_ctx: MasterAdminContext = Depends(require_platform),
    db: Session = Depends(get_db),
):
    """Fetch platform-wide MFA policy (Master Admin only)."""
    policy = MfaService.get_platform_mfa_policy(db)
    return PlatformMfaPolicyResponse(
        enforce_master_admin=policy.get("enforce_master_admin", True),
        enforce_company_admin=policy.get("enforce_company_admin", True),
        enforce_all=policy.get("enforce_all", False),
    )


@router.post(
    "/api/admin/security/mfa-policy",
    response_model=PlatformMfaPolicyResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_PLATFORM))],
)
def update_platform_mfa_policy(
    payload: PlatformMfaPolicyRequest,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_platform),
    db: Session = Depends(get_db),
):
    """Update platform-wide MFA policy with transaction-safe session invalidation (Master Admin only)."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    prev_policy = MfaService.get_platform_mfa_policy(db)
    policy_updates = {k: v for k, v in payload.dict().items() if v is not None}
    updated = MfaService.set_platform_mfa_policy(db, policy_updates, admin_ctx.admin_id)

    # Invalidation coverage across platform transitions:
    if not prev_policy.get("enforce_all") and updated.get("enforce_all"):
        all_tenant_ids = [row[0] for row in db.query(User.id).all()]
        MfaService.invalidate_sessions_for_users(db, all_tenant_ids, reason="platform_enforce_all_mandated")
        MfaService.invalidate_sessions_for_master_admins(db, reason="platform_enforce_all_mandated")
    else:
        if not prev_policy.get("enforce_master_admin") and updated.get("enforce_master_admin"):
            MfaService.invalidate_sessions_for_master_admins(db, reason="platform_master_admin_mandated")
        if not prev_policy.get("enforce_company_admin") and updated.get("enforce_company_admin"):
            from sqlalchemy import or_
            ca_ids = [
                row[0] for row in db.query(User.id)
                .outerjoin(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
                .filter(
                    or_(
                        User.role == UserRole.GLOBAL_ADMIN,
                        UserRoleAssignment.role == "GLOBAL_ADMIN",
                    )
                )
                .distinct()
                .all()
            ]
            MfaService.invalidate_sessions_for_users(db, ca_ids, reason="platform_company_admin_mandated")

    audit.record(
        db=db,
        action=AUTH_MFA_POLICY_UPDATE,
        actor_type=ActorType.MASTER_ADMIN,
        actor_id=admin_ctx.admin_id,
        object_type="security_policy",
        object_id="platform_mfa_policy",
        ip=client_ip,
        user_agent=user_agent,
        metadata={
            "enforce_master_admin": updated.get("enforce_master_admin", True),
            "enforce_company_admin": updated.get("enforce_company_admin", True),
            "enforce_all": updated.get("enforce_all", False),
        },
    )
    db.commit()

    return PlatformMfaPolicyResponse(
        enforce_master_admin=updated.get("enforce_master_admin", True),
        enforce_company_admin=updated.get("enforce_company_admin", True),
        enforce_all=updated.get("enforce_all", False),
    )


# ── 5. ADMIN-ASSISTED MFA RESETS ─────────────────────────────────────────────

@router.post(
    "/api/branch/users/{user_id}/reset-mfa",
    response_model=GenericMessageResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_BRANCH))],
)
def branch_admin_reset_user_mfa(
    user_id: int,
    payload: Optional[AdminMfaResetRequest] = None,
    request: Request = None,
    auth_ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """
    Branch Admin resets MFA for Staff or Uploader within their authorized branch scope.
    Validates tenant isolation, prevents peer/admin resets, and requires re-authentication.
    """
    client_ip = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("user-agent", "") if request else ""

    # 1. Administrator Re-Authentication if confirm_password provided
    if payload and payload.confirm_password:
        caller_user = db.query(User).filter_by(id=auth_ctx.user_id).first()
        if not caller_user or not verify_password(payload.confirm_password, caller_user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Administrator re-authentication failed: Incorrect password.")

    # 2. Tenant boundary validation (returns 404 for cross-company to block ID probing)
    target_user = db.query(User).filter_by(id=user_id, company_id=auth_ctx.company_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # 3. Cannot reset self
    if target_user.id == auth_ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: You cannot reset your own MFA.")

    # 4. Resolve target user's active effective roles (reusing authorization architecture)
    target_roles = _resolve_user_effective_roles(target_user, db)
    if "GLOBAL_ADMIN" in target_roles or "ADMIN" in target_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Branch Administrators cannot reset administrator accounts.",
        )

    # 5. Resolve target user's active branch affiliations
    target_branches = {target_user.branch_id}
    from app.models import UserRoleAssignment
    for a in db.query(UserRoleAssignment).filter_by(user_id=target_user.id).all():
        if a.scope_type == "branch" and a.scope_id:
            target_branches.add(int(a.scope_id))

    # 6. Derive caller's active Branch Admin scopes (strictly from active ADMIN assignments)
    caller_admin_branches = set()
    if auth_ctx.role == UserRole.ADMIN and auth_ctx.branch_id:
        caller_admin_branches.add(auth_ctx.branch_id)
    for a in auth_ctx.assignments:
        if a.get("scope_type") == "branch" and a.get("role") == "ADMIN" and a.get("scope_id"):
            caller_admin_branches.add(int(a["scope_id"]))

    if not auth_ctx.is_global_admin and not (target_branches & caller_admin_branches):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Target user does not belong to any branch within your active administrative scope.",
        )

    # 7. Execute atomic reset and session revocation
    MfaService.reset_mfa_by_admin(db, "user", target_user.id)

    audit.record(
        db=db,
        action=AUTH_MFA_RESET_BY_ADMIN,
        actor_type=ActorType.COMPANY_USER,
        actor_id=auth_ctx.user_id,
        company_id=auth_ctx.company_id,
        branch_id=auth_ctx.branch_id,
        object_type="user",
        object_id=str(target_user.id),
        ip=client_ip,
        user_agent=user_agent,
        metadata={
            "target_user_id": target_user.id,
            "email": target_user.email,
            "reason": payload.reason if payload else "Branch Admin Reset",
        },
    )
    db.commit()

    return GenericMessageResponse(message=f"MFA configuration reset successfully for {target_user.email}.")


@router.post(
    "/api/company/users/{user_id}/mfa-reset-request",
    response_model=GenericMessageResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_COMPANY))],
)
@router.post(
    "/api/company/users/{user_id}/reset-mfa",
    response_model=GenericMessageResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_COMPANY))],
)
def company_admin_reset_user_mfa(
    user_id: int,
    payload: Optional[AdminMfaResetRequest] = None,
    request: Request = None,
    auth_ctx: AuthContext = Depends(require_company),
    db: Session = Depends(get_db),
):
    """
    Company Admin resets MFA for Branch Admins, Staff, or Uploaders within their company.
    Cannot reset peer Company Admins or self.
    """
    client_ip = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("user-agent", "") if request else ""

    # Re-authentication if confirm_password provided
    if payload and payload.confirm_password:
        caller_user = db.query(User).filter_by(id=auth_ctx.user_id).first()
        if not caller_user or not verify_password(payload.confirm_password, caller_user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Administrator re-authentication failed: Incorrect password.")

    # 1. Tenant boundary check
    target_user = db.query(User).filter_by(id=user_id, company_id=auth_ctx.company_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found within your company.",
        )

    # 2. Cannot reset self
    if target_user.id == auth_ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: You cannot reset your own MFA.")

    # 3. Cannot reset peer Company Admin
    target_roles = _resolve_user_effective_roles(target_user, db)
    if "GLOBAL_ADMIN" in target_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: Company Administrators cannot reset peer Company Administrators. Contact Master Admin.",
        )

    MfaService.reset_mfa_by_admin(db, "user", target_user.id)

    audit.record(
        db=db,
        action=AUTH_MFA_RESET_BY_ADMIN,
        actor_type=ActorType.COMPANY_USER,
        actor_id=auth_ctx.user_id,
        company_id=auth_ctx.company_id,
        branch_id=auth_ctx.branch_id,
        object_type="user",
        object_id=str(target_user.id),
        ip=client_ip,
        user_agent=user_agent,
        metadata={
            "target_user_id": target_user.id,
            "email": target_user.email,
            "reason": payload.reason if payload else "Company Admin Reset",
        },
    )
    db.commit()

    return GenericMessageResponse(message=f"MFA configuration reset successfully for {target_user.email}.")


@router.post(
    "/api/admin/users/{user_id}/reset-mfa",
    response_model=GenericMessageResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_PLATFORM))],
)
def platform_admin_reset_user_mfa(
    user_id: int,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_platform),
    db: Session = Depends(get_db),
):
    """Master Admin resets MFA for any company user or company administrator."""
    client_ip = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("user-agent", "") if request else ""

    target_user = db.query(User).filter_by(id=user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    MfaService.reset_mfa_by_admin(db, "user", target_user.id)

    audit.record(
        db=db,
        action=AUTH_MFA_RESET_BY_ADMIN,
        actor_type=ActorType.MASTER_ADMIN,
        actor_id=admin_ctx.admin_id,
        company_id=target_user.company_id,
        branch_id=target_user.branch_id,
        object_type="user",
        object_id=str(target_user.id),
        ip=client_ip,
        user_agent=user_agent,
        metadata={"target_user_id": target_user.id, "email": target_user.email},
    )
    db.commit()

    return GenericMessageResponse(message=f"MFA configuration reset successfully for {target_user.email}.")


@router.post(
    "/api/admin/master-admins/{admin_id}/reset-mfa",
    response_model=GenericMessageResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_PLATFORM))],
)
def platform_admin_reset_master_admin_mfa(
    admin_id: int,
    request: Request,
    admin_ctx: MasterAdminContext = Depends(require_platform),
    db: Session = Depends(get_db),
):
    """Master Admin resets MFA for another master administrator (peer reset)."""
    client_ip = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("user-agent", "") if request else ""

    target_admin = db.query(MasterAdmin).filter_by(id=admin_id).first()
    if not target_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Master Admin not found.")

    MfaService.reset_mfa_by_admin(db, "master_admin", target_admin.id)

    audit.record(
        db=db,
        action=AUTH_MFA_RESET_BY_ADMIN,
        actor_type=ActorType.MASTER_ADMIN,
        actor_id=admin_ctx.admin_id,
        object_type="master_admin",
        object_id=str(target_admin.id),
        ip=client_ip,
        user_agent=user_agent,
        metadata={"target_admin_id": target_admin.id, "email": target_admin.email},
    )
    db.commit()

    return GenericMessageResponse(message=f"MFA configuration reset successfully for {target_admin.email}.")
