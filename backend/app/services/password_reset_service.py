"""
Password recovery and authenticated change-password service.

Enforces:
  1. Anti-enumeration: Uniform responses on reset requests.
  2. Single-use reset tokens with SHA-256 storage and strict expiration.
  3. Immediate invalidation of all existing sessions upon password reset.
  4. Forced password change clearing.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.config import settings
from app.models import (
    AccountStatus,
    MasterAdmin,
    PasswordReset,
    User,
    UserRole,
)
from app.services.email_service import email_service
from app.services.session_service import session_service

logger = logging.getLogger("dms.password_resets")


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class PasswordResetService:
    @staticmethod
    def request_password_reset(
        db: Session,
        email: str,
        portal: str,
        requested_ip: Optional[str] = None,
    ) -> str:
        """
        Request a password reset link.
        Always returns a uniform generic message regardless of whether the account exists.
        """
        normalized_email = email.strip().lower()
        public_message = "If the account is eligible, password reset instructions will be sent."

        if portal == "platform":
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
            if admin and admin.status == AccountStatus.ACTIVE:
                raw_token = secrets.token_hex(32)
                token_hash = hash_token(raw_token)
                expires_at = datetime.utcnow() + timedelta(
                    minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
                )

                pr = PasswordReset(
                    identity_type="master_admin",
                    master_admin_id=admin.id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                    requested_ip=requested_ip[:64] if requested_ip else None,
                    created_at=datetime.utcnow(),
                )
                db.add(pr)
                db.commit()

                email_service.send_password_reset_email(
                    to_email=normalized_email,
                    portal_name="Platform Administration",
                    raw_token=raw_token,
                )

        elif portal in ("company", "app"):
            user = db.query(User).filter(User.email == normalized_email).first()
            eligible = False
            if user and user.status == AccountStatus.ACTIVE:
                if portal == "company" and user.role == UserRole.GLOBAL_ADMIN:
                    eligible = True
                elif portal == "app" and user.role in (UserRole.ADMIN, UserRole.STAFF):
                    eligible = True

            if user and eligible:
                raw_token = secrets.token_hex(32)
                token_hash = hash_token(raw_token)
                expires_at = datetime.utcnow() + timedelta(
                    minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
                )

                pr = PasswordReset(
                    identity_type="user",
                    user_id=user.id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                    requested_ip=requested_ip[:64] if requested_ip else None,
                    created_at=datetime.utcnow(),
                )
                db.add(pr)
                db.commit()

                portal_title = "Company Admin" if portal == "company" else "Branch Workspace"
                email_service.send_password_reset_email(
                    to_email=normalized_email,
                    portal_name=portal_title,
                    raw_token=raw_token,
                )

        return public_message

    @staticmethod
    def reset_password(db: Session, raw_token: str, new_password: str) -> None:
        """
        Redeem a password reset token and update password atomically.
        Revokes all existing sessions.
        """
        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset token is required.",
            )

        if not new_password or len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters.",
            )

        token_hash = hash_token(raw_token)
        pr = (
            db.query(PasswordReset)
            .filter(PasswordReset.token_hash == token_hash)
            .with_for_update()
            .first()
        )

        if not pr or pr.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or already used password reset token.",
            )

        if pr.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This password reset token has expired.",
            )

        # Update password hash and revoke sessions
        hashed = get_password_hash(new_password)
        if pr.identity_type == "master_admin":
            admin = db.query(MasterAdmin).filter(MasterAdmin.id == pr.master_admin_id).first()
            if not admin:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
            admin.password_hash = hashed
            admin.token_version = (admin.token_version or 1) + 1
            admin.must_change_password = False
            admin.failed_attempts = 0
            admin.locked_until = None
            session_service.revoke_all_sessions(db, "master_admin", admin.id, reason="password_reset")

        elif pr.identity_type == "user":
            user = db.query(User).filter(User.id == pr.user_id).first()
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
            user.password_hash = hashed
            user.token_version = (user.token_version or 1) + 1
            user.must_change_password = False
            user.failed_attempts = 0
            user.locked_until = None
            session_service.revoke_all_sessions(db, "user", user.id, reason="password_reset")

        pr.used_at = datetime.utcnow()
        db.commit()
        logger.info("Password successfully reset via token for identity_type=%s", pr.identity_type)

    @staticmethod
    def change_password(
        db: Session,
        identity_type: str,
        identity_id: int,
        current_password: str,
        new_password: str,
    ) -> None:
        """
        Authenticated password change. Verifies current password and clears must_change_password.
        """
        if not new_password or len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters.",
            )

        if identity_type == "master_admin":
            admin = db.query(MasterAdmin).filter(MasterAdmin.id == identity_id).first()
            if not admin or not verify_password(current_password, admin.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect.",
                )
            admin.password_hash = get_password_hash(new_password)
            admin.token_version = (admin.token_version or 1) + 1
            admin.must_change_password = False
            db.commit()
            logger.info("Master Admin password changed: id=%d", admin.id)

        elif identity_type == "user":
            user = db.query(User).filter(User.id == identity_id).first()
            if not user or not verify_password(current_password, user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect.",
                )
            user.password_hash = get_password_hash(new_password)
            user.token_version = (user.token_version or 1) + 1
            user.must_change_password = False
            db.commit()
            logger.info("User password changed: id=%d", user.id)


password_reset_service = PasswordResetService()
