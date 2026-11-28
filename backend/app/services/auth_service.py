"""
Centralized Authentication Service for all three portals:
  1. Platform Portal (aud="platform", master_admins table)
  2. Company Admin Portal (aud="company", users table where role=GLOBAL_ADMIN)
  3. Branch Application Portal (aud="app", users table where role in (ADMIN, STAFF))

Enforces:
  - Account lockout and failed attempt tracking.
  - Portal role eligibility checks (cross-portal login rejection).
  - Company suspension validation.
  - Forced password change detection.
  - Durable session creation with rotated refresh tokens.
  - Explicit portal-specific audience JWT issuance.
"""

import logging
import secrets
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import create_access_token, verify_password
from app.config import settings
from app.models import (
    AccountStatus,
    CompanyStatus,
    MasterAdmin,
    User,
    UserRole,
)
from app.schemas import MasterAdminOut, UserOut, UserRoleAssignmentOut
from app.services.rate_limit_service import rate_limit_service
from app.services.session_service import session_service

logger = logging.getLogger("dms.auth_service")


class AuthService:
    @staticmethod
    def authenticate_portal(
        db: Session,
        email: str,
        password: str,
        portal: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Authenticate an identity against the specified portal.
        Returns:
            dict containing access_token, refresh_token, portal, user info, must_change_password
        """
        normalized_portal = (portal or "app").strip().lower()
        if normalized_portal not in ("platform", "company", "app"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid portal '{portal}'. Valid portals are 'platform', 'company', 'app'.",
            )

        normalized_email = email.strip().lower()

        # ── 1. PLATFORM PORTAL ──────────────────────────────────────────────
        if normalized_portal == "platform":
            admin = (
                db.query(MasterAdmin)
                .filter(
                    or_(
                        MasterAdmin.email == normalized_email,
                        MasterAdmin.email == normalized_email.split("@")[0],
                        MasterAdmin.email == f"{normalized_email}@gmail.com",
                    )
                )
                .first()
            )

            if not admin:
                logger.warning("Platform login failed: unknown MasterAdmin email %s", normalized_email)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password.",
                )

            # Check lockout
            rate_limit_service.check_lockout(admin)

            # Verify password
            if not verify_password(password, admin.password_hash):
                rate_limit_service.record_failed_attempt(db, admin)
                logger.warning("Platform login failed: bad password for %s", normalized_email)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password.",
                )

            # Check status
            if admin.status != AccountStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Administrator account is inactive or locked.",
                )

            # Check MFA status & platform mandatory policy
            from app.services.mfa_service import MfaService
            _master_admin_mfa_enforced = MfaService.is_mfa_mandatory_for_master_admin(db, admin)
            if _master_admin_mfa_enforced and MfaService.is_mfa_enabled(db, "master_admin", admin.id):
                token_claims = {
                    "sub": admin.email,
                    "master_admin_id": admin.id,
                    "identity_type": "master_admin",
                    "role": "MASTER_ADMIN",
                    "token_type": "mfa_pending",
                    "token_version": admin.token_version,
                    "jti": secrets.token_hex(16),
                }
                mfa_token = create_access_token(
                    data=token_claims,
                    expires_delta=timedelta(minutes=settings.MFA_PENDING_TOKEN_EXPIRE_MINUTES),
                    audience=settings.JWT_AUDIENCE_PLATFORM,
                )
                return {
                    "mfa_required": True,
                    "mfa_pending_token": mfa_token,
                    "portal": "platform",
                }

            if MfaService.is_mfa_mandatory_for_master_admin(db, admin):
                token_claims = {
                    "sub": admin.email,
                    "master_admin_id": admin.id,
                    "identity_type": "master_admin",
                    "role": "MASTER_ADMIN",
                    "token_type": "mfa_enrollment_required",
                    "token_version": admin.token_version,
                    "jti": secrets.token_hex(16),
                }
                enroll_token = create_access_token(
                    data=token_claims,
                    expires_delta=timedelta(minutes=settings.MFA_PENDING_TOKEN_EXPIRE_MINUTES),
                    audience=settings.JWT_AUDIENCE_PLATFORM,
                )
                return {
                    "mfa_enrollment_required": True,
                    "mfa_enrollment_token": enroll_token,
                    "portal": "platform",
                }

            # Successful auth
            rate_limit_service.record_successful_login(db, admin)

            # Create refresh session
            session, raw_refresh_token = session_service.create_session(
                db=db,
                identity_type="master_admin",
                identity_id=admin.id,
                user_agent=user_agent,
                ip_address=ip_address,
            )

            # Build platform JWT claims
            token_claims = {
                "sub": admin.email,
                "master_admin_id": admin.id,
                "identity_type": "master_admin",
                "role": "MASTER_ADMIN",
                "token_version": admin.token_version,
                "jti": secrets.token_hex(16),
            }
            access_token = create_access_token(
                data=token_claims,
                audience=settings.JWT_AUDIENCE_PLATFORM,
            )

            admin_out = MasterAdminOut(
                id=admin.id,
                name=admin.name,
                email=admin.email,
                role="MASTER_ADMIN",
                portal="platform",
                status=admin.status.value,
            )

            return {
                "access_token": access_token,
                "refresh_token": raw_refresh_token,
                "token_type": "bearer",
                "portal": "platform",
                "must_change_password": admin.must_change_password,
                "user": admin_out,
            }

        # ── 2 & 3. TENANT PORTALS (COMPANY & APP) ───────────────────────────
        user = db.query(User).filter(User.email == normalized_email).first()

        if not user:
            logger.warning("Tenant login failed: unknown email %s for portal %s", normalized_email, normalized_portal)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
            )

        # Check lockout
        rate_limit_service.check_lockout(user)

        # Verify password
        if not verify_password(password, user.password_hash):
            rate_limit_service.record_failed_attempt(db, user)
            logger.warning("Tenant login failed: bad password for %s", normalized_email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
            )

        # Check account status
        if user.status != AccountStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive or locked.",
            )

        # Check company suspension: fail closed for all company users
        if user.company and user.company.status == CompanyStatus.SUSPENDED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company account is suspended. Contact system administrator.",
            )

        # Enforce portal role eligibility
        if normalized_portal == "company":
            if user.role != UserRole.GLOBAL_ADMIN:
                logger.warning(
                    "Cross-portal access denied: user %s (role=%s) cannot access Company Admin Portal",
                    user.email,
                    user.role.value,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Account is not authorized for the Company Admin Portal.",
                )
            target_audience = settings.JWT_AUDIENCE_COMPANY

        elif normalized_portal == "app":
            if user.role not in (UserRole.ADMIN, UserRole.STAFF, UserRole.UPLOADER):
                logger.warning(
                    "Cross-portal access denied: user %s (role=%s) cannot access Branch Workspace Portal",
                    user.email,
                    user.role.value,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Account is not authorized for the Branch Workspace Portal. Use the Company Portal.",
                )
            target_audience = settings.JWT_AUDIENCE_APP

        # Check MFA status & company/platform mandatory policy
        from app.services.mfa_service import MfaService
        _user_mfa_enforced = MfaService.is_mfa_mandatory_for_user(db, user)
        if _user_mfa_enforced and MfaService.is_mfa_enabled(db, "user", user.id):
            token_claims = {
                "sub": user.email,
                "uid": user.id,
                "user_id": user.id,
                "company_id": user.company_id,
                "branch_id": user.branch_id,
                "tenant_id": user.branch_id,
                "role": user.role.value,
                "identity_type": "user",
                "token_type": "mfa_pending",
                "token_version": user.token_version,
                "jti": secrets.token_hex(16),
            }
            mfa_token = create_access_token(
                data=token_claims,
                expires_delta=timedelta(minutes=settings.MFA_PENDING_TOKEN_EXPIRE_MINUTES),
                audience=target_audience,
            )
            return {
                "mfa_required": True,
                "mfa_pending_token": mfa_token,
                "portal": normalized_portal,
            }

        if MfaService.is_mfa_mandatory_for_user(db, user):
            token_claims = {
                "sub": user.email,
                "uid": user.id,
                "user_id": user.id,
                "company_id": user.company_id,
                "branch_id": user.branch_id,
                "tenant_id": user.branch_id,
                "role": user.role.value,
                "identity_type": "user",
                "token_type": "mfa_enrollment_required",
                "token_version": user.token_version,
                "jti": secrets.token_hex(16),
            }
            enroll_token = create_access_token(
                data=token_claims,
                expires_delta=timedelta(minutes=settings.MFA_PENDING_TOKEN_EXPIRE_MINUTES),
                audience=target_audience,
            )
            return {
                "mfa_enrollment_required": True,
                "mfa_enrollment_token": enroll_token,
                "portal": normalized_portal,
            }

        # Successful auth
        rate_limit_service.record_successful_login(db, user)

        # Create refresh session
        session, raw_refresh_token = session_service.create_session(
            db=db,
            identity_type="user",
            identity_id=user.id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        # Build tenant JWT claims
        token_claims = {
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
        access_token = create_access_token(
            data=token_claims,
            audience=target_audience,
        )

        company_name = user.company.name if user.company else ""
        company_display_name = user.company.display_name if user.company else None
        company_logo_url = user.company.logo_url if user.company else None
        branch_name = user.branch.name if user.branch else ""
        branch_code = user.branch.code if user.branch else ""

        from app.context import resolve_user_permissions_and_assignments
        perms, assignments = resolve_user_permissions_and_assignments(user, db)

        user_out = UserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            company_id=user.company_id,
            company_name=company_name,
            company_display_name=company_display_name,
            company_logo_url=company_logo_url,
            branch_id=user.branch_id,
            branch_name=branch_name,
            branch_code=branch_code,
            permissions=sorted(list(perms)),
            assignments=[UserRoleAssignmentOut(**a) for a in assignments],
            tenant_id=user.branch_id,
            tenant_name=branch_name,
        )

        return {
            "access_token": access_token,
            "refresh_token": raw_refresh_token,
            "token_type": "bearer",
            "portal": normalized_portal,
            "must_change_password": user.must_change_password,
            "user": user_out,
        }


auth_service = AuthService()
