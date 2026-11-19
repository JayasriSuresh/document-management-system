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
from app.auth.permissions import MFA_MANAGE_COMPANY, MFA_MANAGE_PLATFORM
from app.auth.role_permissions import ROLE_GLOBAL_ADMIN
from app.config import settings
from app.context import (
    AuthContext,
    MasterAdminContext,
    _build_auth_context,
    _build_master_admin_context,
    require_company,
    require_platform,
)
from app.database import get_db
from app.models import (
    AccountStatus,
    Company,
    CompanyStatus,
    MasterAdmin,
    User,
    UserRole,
)
from app.schemas import (
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
    """
    ident = _resolve_caller_identity(request, db, authorization, allow_enrollment_token=False)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

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
    """
    ident = _resolve_caller_identity(request, db, authorization, allow_enrollment_token=False)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

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


# ── 4. COMPANY & PLATFORM MFA POLICIES ───────────────────────────────────────

@router.get(
    "/api/company/security/mfa-policy",
    response_model=CompanyMfaPolicyResponse,
    dependencies=[Depends(require_permission(MFA_MANAGE_COMPANY))],
)
def get_company_mfa_policy(
    auth_ctx: AuthContext = Depends(require_company),
    db: Session = Depends(get_db),
):
    """Fetch company MFA policy (Company Admin only)."""
    company = db.query(Company).filter_by(id=auth_ctx.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    return CompanyMfaPolicyResponse(
        company_id=company.id,
        mfa_required_for_all=bool(company.mfa_required_for_all),
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
    """Update company MFA policy (Company Admin only)."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    company = db.query(Company).filter_by(id=auth_ctx.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    company.mfa_required_for_all = payload.mfa_required_for_all
    company.updated_at = datetime.utcnow()

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
        metadata={"mfa_required_for_all": company.mfa_required_for_all},
    )
    db.commit()

    return CompanyMfaPolicyResponse(
        company_id=company.id,
        mfa_required_for_all=company.mfa_required_for_all,
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
    """Update platform-wide MFA policy (Master Admin only)."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    policy_updates = {k: v for k, v in payload.dict().items() if v is not None}
    updated = MfaService.set_platform_mfa_policy(db, policy_updates, admin_ctx.admin_id)

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
    request: Request,
    auth_ctx: AuthContext = Depends(require_company),
    db: Session = Depends(get_db),
):
    """
    Company Admin resets MFA for a user within their company.
    Enforces company tenant boundary. Invalidates user sessions.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    target_user = db.query(User).filter_by(id=user_id, company_id=auth_ctx.company_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found within your company.",
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
        metadata={"target_user_id": target_user.id, "email": target_user.email},
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
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

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
    """Master Admin resets MFA for another master administrator."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

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
