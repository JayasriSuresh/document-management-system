"""
Authentication & Identity Router for DMS (Module 3).

Centralized routes:
  - POST /api/auth/login                  (portal-aware centralized login)
  - POST /api/auth/refresh                (refresh token rotation & replay detection)
  - POST /api/auth/logout                 (revoke current session, clear cookie)
  - POST /api/auth/logout-all             (revoke all sessions, increment token_version)
  - POST /api/auth/invite                 (company/branch user invitation)
  - POST /api/auth/invite/accept          (accept invitation & provision account)
  - POST /api/auth/password/reset-request (anti-enumeration password recovery)
  - POST /api/auth/password/reset         (redeem reset token)
  - POST /api/auth/password/change        (authenticated password change)
  - GET  /api/auth/me                     (identity info for current portal)
"""

import logging
import secrets
from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, decode_token, oauth2_scheme
from app.auth.dependencies import require_permission, requires
from app.auth.permissions import USER_INVITE
from app.config import settings
from app.context import (
    AuthContext,
    MasterAdminContext,
    get_auth_context,
    require_company,
    require_portal,
)
from app.database import get_db
from app.models import (
    AccountStatus,
    CompanyStatus,
    MasterAdmin,
    User,
    UserRole,
)
from app.schemas import (
    GenericMessageResponse,
    InviteAcceptRequest,
    InviteRequest,
    LoginRequest,
    MasterAdminOut,
    PasswordChangeRequest,
    PasswordResetRequest,
    PasswordResetSubmit,
    TokenResponse,
    UserOut,
    UserRoleAssignmentOut,
)
from app.services.auth_service import auth_service
from app.services.invitation_service import invitation_service
from app.services.password_reset_service import password_reset_service
from app.services.rate_limit_service import rate_limit_service
from app.services.session_service import session_service
from app.audit import (
    audit,
    ActorType,
    AUTH_LOGIN_SUCCESS,
    AUTH_LOGIN_FAILURE,
    AUTH_LOGOUT,
    AUTH_LOGOUT_ALL,
    AUTH_TOKEN_REFRESH,
    AUTH_INVITATION_CREATE,
    AUTH_INVITATION_ACCEPT,
    AUTH_PASSWORD_CHANGE,
    AUTH_PASSWORD_RESET_REQUEST,
    AUTH_PASSWORD_RESET_SUCCESS,
)

logger = logging.getLogger("dms.routers.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── 1. LOGIN ──────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(
    request_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    rate_limit_service.check_ip_rate_limit(request, action="login", max_requests=25, window_seconds=60)

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    # Backward compatibility: if portal not specified or None, infer from user role if possible
    chosen_portal = request_data.portal
    if not chosen_portal:
        user = db.query(User).filter(User.email == request_data.email.strip().lower()).first()
        if user and user.role == UserRole.GLOBAL_ADMIN:
            chosen_portal = "company"
        else:
            chosen_portal = "app"

    try:
        result = auth_service.authenticate_portal(
            db=db,
            email=request_data.email,
            password=request_data.password,
            portal=chosen_portal,
            user_agent=user_agent,
            ip_address=client_ip,
        )

        # Intermediate MFA challenge or mandatory enrollment required
        if result.get("mfa_required"):
            return TokenResponse(
                mfa_required=True,
                mfa_pending_token=result["mfa_pending_token"],
                portal=result["portal"],
            )

        if result.get("mfa_enrollment_required"):
            return TokenResponse(
                mfa_enrollment_required=True,
                mfa_enrollment_token=result["mfa_enrollment_token"],
                portal=result["portal"],
            )

        # Successful login audit record committed atomically with the session
        if result["portal"] == "platform":
            audit.record(
                db=db,
                action=AUTH_LOGIN_SUCCESS,
                actor_type=ActorType.MASTER_ADMIN,
                actor_id=result["user"].id,
                object_type="master_admin",
                object_id=result["user"].id,
                ip=client_ip,
                user_agent=user_agent,
                metadata={"email": result["user"].email, "portal": "platform"},
            )
        else:
            user_rec = db.query(User).filter(User.id == result["user"].id).first()
            audit.record(
                db=db,
                action=AUTH_LOGIN_SUCCESS,
                actor_type=ActorType.COMPANY_USER,
                actor_id=result["user"].id,
                company_id=getattr(user_rec, "company_id", None),
                branch_id=getattr(user_rec, "branch_id", None),
                object_type="user",
                object_id=result["user"].id,
                ip=client_ip,
                user_agent=user_agent,
                metadata={"email": result["user"].email, "portal": result["portal"]},
            )
        db.commit()
    except HTTPException as e:
        # Failed login recorded in separate transaction so rollback does not erase the security event
        audit.record_auth_failure(
            action=AUTH_LOGIN_FAILURE,
            email=request_data.email,
            reason=str(e.detail),
            request=request,
            actor_type=ActorType.ANONYMOUS,
        )
        raise e

    # Set secure HttpOnly cookie for the refresh token
    response.set_cookie(
        key="dms_refresh_token",
        value=result["refresh_token"],
        httponly=True,
        secure=settings.is_cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )

    return TokenResponse(
        access_token=result["access_token"],
        token_type="bearer",
        portal=result["portal"],
        must_change_password=result["must_change_password"],
        user=result["user"],
    )


# ── 2. REFRESH TOKEN ROTATION ────────────────────────────────────────────────

@router.post("/refresh")
def refresh_session(
    request: Request,
    response: Response,
    dms_refresh_token: Optional[str] = Cookie(None),
    payload_data: Optional[Dict[str, str]] = None,
    db: Session = Depends(get_db),
):
    rate_limit_service.check_ip_rate_limit(request, action="refresh", max_requests=30, window_seconds=60)

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    raw_token = dms_refresh_token or (payload_data.get("refresh_token") if payload_data else None)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required in cookie or request body.",
        )

    new_session, new_raw_token, identity = session_service.rotate_session(
        db=db,
        raw_token=raw_token,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    # Record token refresh event in the same transaction
    audit.record_event(
        db=db,
        action=AUTH_TOKEN_REFRESH,
        request=request,
        ctx=identity,
        object_type="session",
        object_id=new_session.id,
    )
    db.commit()

    # Issue new access token matching identity's portal
    if isinstance(identity, MasterAdmin):
        claims = {
            "sub": identity.email,
            "master_admin_id": identity.id,
            "identity_type": "master_admin",
            "role": "MASTER_ADMIN",
            "token_version": identity.token_version,
            "jti": secrets.token_hex(16),
        }
        access_token = create_access_token(claims, audience=settings.JWT_AUDIENCE_PLATFORM)
    elif isinstance(identity, User):
        target_aud = (
            settings.JWT_AUDIENCE_COMPANY
            if identity.role == UserRole.GLOBAL_ADMIN
            else settings.JWT_AUDIENCE_APP
        )
        claims = {
            "sub": identity.email,
            "uid": identity.id,
            "user_id": identity.id,
            "company_id": identity.company_id,
            "branch_id": identity.branch_id,
            "tenant_id": identity.branch_id,
            "role": identity.role.value,
            "identity_type": "user",
            "token_version": identity.token_version,
            "jti": secrets.token_hex(16),
        }
        access_token = create_access_token(claims, audience=target_aud)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown identity type.")

    # Update cookie with new rotated refresh token
    response.set_cookie(
        key="dms_refresh_token",
        value=new_raw_token,
        httponly=True,
        secure=settings.is_cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "must_change_password": identity.must_change_password,
    }


# ── 3. LOGOUT ─────────────────────────────────────────────────────────────────

@router.post("/logout", response_model=GenericMessageResponse)
def logout(
    request: Request,
    response: Response,
    dms_refresh_token: Optional[str] = Cookie(None),
    payload_data: Optional[Dict[str, str]] = None,
    db: Session = Depends(get_db),
):
    raw_token = dms_refresh_token or (payload_data.get("refresh_token") if payload_data else None)
    if raw_token:
        session_service.revoke_session(db, raw_token, reason="logout")

    actor_type = ActorType.ANONYMOUS
    actor_id = None
    company_id = None
    branch_id = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ", 1)[1]
            token_payload = decode_token(token)
            if token_payload.get("identity_type") == "master_admin":
                actor_type = ActorType.MASTER_ADMIN
                actor_id = token_payload.get("master_admin_id")
            else:
                actor_type = ActorType.COMPANY_USER
                actor_id = token_payload.get("user_id") or token_payload.get("uid")
                company_id = token_payload.get("company_id")
                branch_id = token_payload.get("branch_id")
        except Exception:
            pass

    audit.record(
        db=db,
        action=AUTH_LOGOUT,
        actor_type=actor_type,
        actor_id=actor_id,
        company_id=company_id,
        branch_id=branch_id,
        metadata={"reason": "logout"},
        ip=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        request_id=getattr(getattr(request, "state", None), "request_id", None) if request else None,
    )
    db.commit()

    response.delete_cookie(key="dms_refresh_token", path="/")
    return GenericMessageResponse(message="Successfully logged out.")


# ── 4. LOGOUT ALL SESSIONS ───────────────────────────────────────────────────

@router.post("/logout-all", response_model=GenericMessageResponse)
def logout_all(
    request: Request,
    response: Response,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = decode_token(token)
    identity_type = payload.get("identity_type", "user")

    if identity_type == "master_admin":
        admin_id = payload.get("master_admin_id")
        if not admin_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        session_service.revoke_all_sessions(db, "master_admin", admin_id, reason="logout_all")
        audit.record(
            db=db,
            action=AUTH_LOGOUT_ALL,
            actor_type=ActorType.MASTER_ADMIN,
            actor_id=admin_id,
            object_type="master_admin",
            object_id=admin_id,
            metadata={"revocation_type": "all_sessions"},
        )
    else:
        user_id = payload.get("user_id") or payload.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        session_service.revoke_all_sessions(db, "user", user_id, reason="logout_all")
        user_rec = db.query(User).filter(User.id == user_id).first()
        audit.record(
            db=db,
            action=AUTH_LOGOUT_ALL,
            actor_type=ActorType.COMPANY_USER,
            actor_id=user_id,
            company_id=getattr(user_rec, "company_id", None),
            branch_id=getattr(user_rec, "branch_id", None),
            object_type="user",
            object_id=user_id,
            metadata={"revocation_type": "all_sessions"},
        )
    db.commit()

    response.delete_cookie(key="dms_refresh_token", path="/")
    return GenericMessageResponse(message="All active sessions revoked successfully.")


# ── 5. USER INVITATIONS ──────────────────────────────────────────────────────

@router.post("/invite", response_model=GenericMessageResponse)
@requires(USER_INVITE)
def invite_user(
    req: InviteRequest,
    request: Request,
    auth_ctx: AuthContext = Depends(require_permission(USER_INVITE)),
    db: Session = Depends(get_db),
):
    rate_limit_service.check_ip_rate_limit(request, action="invite", max_requests=20, window_seconds=60)

    invitation = invitation_service.create_invitation(
        db=db,
        auth=auth_ctx,
        email=req.email,
        branch_id=req.branch_id,
        invited_role=req.invited_role,
    )
    audit.record_event(
        db=db,
        action=AUTH_INVITATION_CREATE,
        request=request,
        ctx=auth_ctx,
        object_type="invitation",
        object_id=getattr(invitation, "id", None),
        metadata={"email": req.email, "role": req.invited_role, "branch_id": req.branch_id},
    )
    db.commit()
    return GenericMessageResponse(message=f"Invitation successfully dispatched to {req.email}.")


@router.post("/invite/accept", response_model=GenericMessageResponse)
def accept_invite(
    req: InviteAcceptRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limit_service.check_ip_rate_limit(request, action="invite_accept", max_requests=10, window_seconds=60)

    user = invitation_service.accept_invitation(
        db=db,
        raw_token=req.token,
        name=req.name,
        password=req.password,
    )
    audit.record_event(
        db=db,
        action=AUTH_INVITATION_ACCEPT,
        request=request,
        ctx=user,
        object_type="user",
        object_id=user.id,
        metadata={"email": user.email, "name": user.name},
        company_id=user.company_id,
        branch_id=user.branch_id,
    )
    db.commit()
    return GenericMessageResponse(message=f"Invitation accepted. Account for {user.email} is ready. You may now log in.")


# ── 6. PASSWORD RESET ────────────────────────────────────────────────────────

@router.post("/password/reset-request", response_model=GenericMessageResponse)
def request_password_reset(
    req: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limit_service.check_ip_rate_limit(request, action="reset_request", max_requests=10, window_seconds=60)
    client_ip = request.client.host if request.client else "unknown"

    msg = password_reset_service.request_password_reset(
        db=db,
        email=req.email,
        portal=req.portal or "app",
        requested_ip=client_ip,
    )
    audit.record_event(
        db=db,
        action=AUTH_PASSWORD_RESET_REQUEST,
        request=request,
        object_type="user",
        metadata={"email": req.email},
    )
    db.commit()
    return GenericMessageResponse(message=msg)


@router.post("/password/reset", response_model=GenericMessageResponse)
def reset_password(
    req: PasswordResetSubmit,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limit_service.check_ip_rate_limit(request, action="reset_submit", max_requests=10, window_seconds=60)

    password_reset_service.reset_password(
        db=db,
        raw_token=req.token,
        new_password=req.new_password,
    )
    audit.record_event(
        db=db,
        action=AUTH_PASSWORD_RESET_SUCCESS,
        request=request,
        object_type="user",
    )
    db.commit()
    return GenericMessageResponse(message="Password reset successfully. You may now log in with your new password.")


@router.post("/password/change", response_model=GenericMessageResponse)
def change_password(
    req: PasswordChangeRequest,
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = decode_token(token)
    identity_type = payload.get("identity_type", "user")

    if identity_type == "master_admin":
        admin_id = payload.get("master_admin_id")
        password_reset_service.change_password(
            db=db,
            identity_type="master_admin",
            identity_id=admin_id,
            current_password=req.current_password,
            new_password=req.new_password,
        )
        audit.record(
            db=db,
            action=AUTH_PASSWORD_CHANGE,
            actor_type=ActorType.MASTER_ADMIN,
            actor_id=admin_id,
            object_type="master_admin",
            object_id=admin_id,
        )
    else:
        user_id = payload.get("user_id") or payload.get("uid")
        password_reset_service.change_password(
            db=db,
            identity_type="user",
            identity_id=user_id,
            current_password=req.current_password,
            new_password=req.new_password,
        )
        user_rec = db.query(User).filter(User.id == user_id).first()
        audit.record(
            db=db,
            action=AUTH_PASSWORD_CHANGE,
            actor_type=ActorType.COMPANY_USER,
            actor_id=user_id,
            company_id=getattr(user_rec, "company_id", None),
            branch_id=getattr(user_rec, "branch_id", None),
            object_type="user",
            object_id=user_id,
        )

    db.commit()
    return GenericMessageResponse(message="Password changed successfully.")


# ── 7. IDENTITY PROFILE (/me) ────────────────────────────────────────────────

@router.get("/me", response_model=Union[UserOut, MasterAdminOut])
def me(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = decode_token(token)
    identity_type = payload.get("identity_type", "user")

    if identity_type == "master_admin":
        admin_id = payload.get("master_admin_id")
        admin = db.query(MasterAdmin).filter(MasterAdmin.id == admin_id).first()
        if not admin or admin.status != AccountStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator account inactive")
        return MasterAdminOut(
            id=admin.id,
            name=admin.name,
            email=admin.email,
            role="MASTER_ADMIN",
            portal="platform",
            status=admin.status.value,
        )

    # Tenant user
    auth_ctx = get_auth_context(token=token, db=db)
    return UserOut(
        id=auth_ctx.user_id,
        name=auth_ctx.user_name,
        email=auth_ctx.user_email,
        role=auth_ctx.role,
        company_id=auth_ctx.company_id,
        company_name=auth_ctx.company_name,
        company_display_name=auth_ctx.company_display_name,
        company_logo_url=auth_ctx.company_logo_url,
        branch_id=auth_ctx.branch_id,
        branch_name=auth_ctx.branch_name,
        branch_code=auth_ctx.branch_code,
        permissions=sorted(list(auth_ctx.permissions)),
        assignments=[UserRoleAssignmentOut(**a) for a in auth_ctx.assignments],
        tenant_id=auth_ctx.branch_id,
        tenant_name=auth_ctx.branch_name,
    )
