"""
Durable session management, refresh token rotation, and replay detection.

Enforces:
  1. Cryptographic hashing of refresh tokens before DB storage.
  2. Automatic rotation on every refresh request.
  3. Replay attack detection: if a rotated token is reused, all descendants in the family are revoked.
  4. Concurrent refresh serialization via row-level locks.
  5. Logout and logout-all session revocation with token_version invalidation.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, Union

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AccountStatus,
    Company,
    CompanyStatus,
    MasterAdmin,
    User,
    UserSession,
)

logger = logging.getLogger("dms.sessions")


def hash_token(raw_token: str) -> str:
    """Return SHA-256 hex digest of a raw token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SessionService:
    @staticmethod
    def create_session(
        db: Session,
        identity_type: str,
        identity_id: int,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        family_id: Optional[str] = None,
        parent_session_id: Optional[int] = None,
    ) -> Tuple[UserSession, str]:
        """
        Create a new persistent refresh session and return (session_record, raw_token).
        Raw token is never saved in the database.
        """
        raw_token = secrets.token_hex(32)
        token_hash = hash_token(raw_token)
        family = family_id or secrets.token_hex(16)
        expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        session = UserSession(
            identity_type=identity_type,
            user_id=identity_id if identity_type == "user" else None,
            master_admin_id=identity_id if identity_type == "master_admin" else None,
            token_hash=token_hash,
            family_id=family,
            parent_session_id=parent_session_id,
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address[:64] if ip_address else None,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow(),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session, raw_token

    @staticmethod
    def rotate_session(
        db: Session,
        raw_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[UserSession, str, Union[User, MasterAdmin]]:
        """
        Validate an incoming refresh token, detect replay attacks, and rotate the session.
        Returns (new_session, new_raw_token, identity).
        """
        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token required",
            )

        token_hash = hash_token(raw_token)

        # Use with_for_update to guard against race conditions on parallel requests
        session = (
            db.query(UserSession)
            .filter(UserSession.token_hash == token_hash)
            .with_for_update()
            .first()
        )

        if not session:
            logger.warning("Refresh attempt with unknown token hash: %s", token_hash[:12])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # ── Replay attack detection ──────────────────────────────────────────
        if session.revoked_at is not None:
            logger.critical(
                "SECURITY ALERT: Refresh token reuse detected! family_id=%s, token_hash=%s",
                session.family_id,
                token_hash[:12],
            )
            from app.audit import audit, AUTH_TOKEN_REPLAY_DETECTED, ActorType
            audit.record(
                db=db,
                action=AUTH_TOKEN_REPLAY_DETECTED,
                actor_type=ActorType.COMPANY_USER if session.identity_type == "user" else ActorType.MASTER_ADMIN,
                actor_id=session.user_id if session.identity_type == "user" else session.master_admin_id,
                object_type="session",
                object_id=session.id,
                ip=ip_address,
                user_agent=user_agent,
                metadata={"family_id": session.family_id, "revocation_type": "replay_attack_detected"},
            )
            # Invalidate all active sessions in this family immediately
            db.query(UserSession).filter(
                UserSession.family_id == session.family_id,
                UserSession.revoked_at.is_(None),
            ).update(
                {
                    "revoked_at": datetime.utcnow(),
                    "revoke_reason": "replay_attack_detected",
                },
                synchronize_session=False,
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token: session compromised",
            )

        # ── Expiration check ─────────────────────────────────────────────────
        if session.expires_at < datetime.utcnow():
            session.revoked_at = datetime.utcnow()
            session.revoke_reason = "expired"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        # ── Identity validation ──────────────────────────────────────────────
        identity: Union[User, MasterAdmin]
        if session.identity_type == "master_admin":
            identity = (
                db.query(MasterAdmin)
                .filter(MasterAdmin.id == session.master_admin_id)
                .first()
            )
            if not identity or identity.status != AccountStatus.ACTIVE:
                session.revoked_at = datetime.utcnow()
                session.revoke_reason = "account_inactive"
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Administrator account is inactive or locked",
                )
        elif session.identity_type == "user":
            identity = db.query(User).filter(User.id == session.user_id).first()
            if not identity or identity.status != AccountStatus.ACTIVE:
                session.revoked_at = datetime.utcnow()
                session.revoke_reason = "account_inactive"
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is inactive or locked",
                )
            # Enforce company suspension check on refresh
            company = db.query(Company).filter(Company.id == identity.company_id).first()
            if not company or company.status == CompanyStatus.SUSPENDED:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Company account is suspended. Contact system administrator.",
                )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown identity type")

        # ── Rotate token: revoke current, issue descendant in same family ────
        session.revoked_at = datetime.utcnow()
        session.revoke_reason = "rotated"
        session.last_used_at = datetime.utcnow()

        new_raw_token = secrets.token_hex(32)
        new_token_hash = hash_token(new_raw_token)
        new_session = UserSession(
            identity_type=session.identity_type,
            user_id=session.user_id,
            master_admin_id=session.master_admin_id,
            token_hash=new_token_hash,
            family_id=session.family_id,
            parent_session_id=session.id,
            user_agent=user_agent[:512] if user_agent else session.user_agent,
            ip_address=ip_address[:64] if ip_address else session.ip_address,
            expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow(),
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)

        return new_session, new_raw_token, identity

    @staticmethod
    def revoke_session(db: Session, raw_token: str, reason: str = "logout") -> bool:
        """Revoke a single session by its raw token."""
        if not raw_token:
            return False
        token_hash = hash_token(raw_token)
        session = (
            db.query(UserSession)
            .filter(UserSession.token_hash == token_hash, UserSession.revoked_at.is_(None))
            .first()
        )
        if session:
            session.revoked_at = datetime.utcnow()
            session.revoke_reason = reason
            db.commit()
            return True
        return False

    @staticmethod
    def revoke_all_sessions(
        db: Session, identity_type: str, identity_id: int, reason: str = "logout_all"
    ) -> int:
        """
        Revoke all active sessions belonging to an identity and increment token_version.
        """
        query = db.query(UserSession).filter(
            UserSession.identity_type == identity_type,
            UserSession.revoked_at.is_(None),
        )
        if identity_type == "user":
            query = query.filter(UserSession.user_id == identity_id)
            user = db.query(User).filter(User.id == identity_id).first()
            if user:
                user.token_version = (user.token_version or 1) + 1
        elif identity_type == "master_admin":
            query = query.filter(UserSession.master_admin_id == identity_id)
            admin = db.query(MasterAdmin).filter(MasterAdmin.id == identity_id).first()
            if admin:
                admin.token_version = (admin.token_version or 1) + 1

        count = query.update(
            {"revoked_at": datetime.utcnow(), "revoke_reason": reason},
            synchronize_session=False,
        )
        db.commit()
        return count


session_service = SessionService()
