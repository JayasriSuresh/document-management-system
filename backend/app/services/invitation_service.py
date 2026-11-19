"""
User invitation service for tenant workspace expansion.

Enforces:
  1. Role escalation prevention (e.g., ADMIN cannot invite GLOBAL_ADMIN).
  2. Strict company & branch scoping (cannot invite into another company's branch).
  3. Single-use invitation tokens with SHA-256 hashing.
  4. Atomic user creation upon acceptance.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.config import settings
from app.context import AuthContext
from app.models import (
    AccountStatus,
    Branch,
    Company,
    CompanyStatus,
    Invitation,
    User,
    UserRole,
)
from app.services.email_service import email_service

logger = logging.getLogger("dms.invitations")


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class InvitationService:
    @staticmethod
    def create_invitation(
        db: Session,
        auth: AuthContext,
        email: str,
        branch_id: int,
        invited_role: UserRole,
    ) -> Tuple[Invitation, str]:
        """
        Create a new invitation scoped strictly to the inviter's company.
        """
        # 1. Permission checks
        if auth.role == UserRole.STAFF:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff members are not authorized to issue user invitations.",
            )

        # 2. Prevent role escalation
        if auth.role == UserRole.ADMIN and invited_role == UserRole.GLOBAL_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Branch Admins cannot invite Global Admins.",
            )

        # 3. Branch admin can only invite to their own branch
        if auth.role == UserRole.ADMIN and branch_id != auth.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Branch Admins can only invite users to their own branch.",
            )

        # 4. Enforce company boundary on branch
        branch = (
            db.query(Branch)
            .filter(Branch.id == branch_id, Branch.company_id == auth.company_id)
            .first()
        )
        if not branch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected branch does not belong to your company.",
            )

        normalized_email = email.strip().lower()

        # 5. Check company user quota (active users + pending active invitations)
        company = db.query(Company).filter(Company.id == auth.company_id).first()
        if company:
            active_users_count = db.query(User).filter(
                User.company_id == auth.company_id,
                User.status == AccountStatus.ACTIVE,
            ).count()
            pending_invites_count = db.query(Invitation).filter(
                Invitation.company_id == auth.company_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > datetime.utcnow(),
                Invitation.email != normalized_email,
            ).count()
            if (active_users_count + pending_invites_count) >= company.max_users:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Company user limit reached: maximum {company.max_users} users allowed.",
                )

        # 6. Check if active user already exists
        existing_user = db.query(User).filter(User.email == normalized_email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address is already registered.",
            )

        # 6. Revoke any existing pending invitations for this email
        db.query(Invitation).filter(
            Invitation.email == normalized_email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        ).update(
            {"revoked_at": datetime.utcnow()},
            synchronize_session=False,
        )

        # 7. Generate secure token
        raw_token = secrets.token_hex(32)
        token_hash = hash_token(raw_token)
        expires_at = datetime.utcnow() + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)

        invitation = Invitation(
            email=normalized_email,
            company_id=auth.company_id,
            branch_id=branch.id,
            invited_role=invited_role,
            token_hash=token_hash,
            invited_by=auth.user_id,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

        # 8. Send invitation email
        email_service.send_invitation_email(
            to_email=normalized_email,
            company_name=auth.company_name,
            branch_name=branch.name,
            role=invited_role.value,
            raw_token=raw_token,
        )

        return invitation, raw_token

    @staticmethod
    def accept_invitation(
        db: Session,
        raw_token: str,
        name: str,
        password: str,
    ) -> User:
        """
        Accept an invitation atomically and provision the new user.
        """
        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation token is required.",
            )

        if not name or len(name.strip()) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Valid name is required.",
            )

        if not password or len(password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters.",
            )

        token_hash = hash_token(raw_token)
        invitation = (
            db.query(Invitation)
            .filter(Invitation.token_hash == token_hash)
            .with_for_update()
            .first()
        )

        if not invitation or invitation.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or revoked invitation token.",
            )

        if invitation.accepted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has already been accepted.",
            )

        if invitation.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation token has expired.",
            )

        # Verify company is active
        company = db.query(Company).filter(Company.id == invitation.company_id).first()
        if not company or company.status != CompanyStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company account is suspended. Cannot accept invitation.",
            )

        # Enforce user quota
        active_count = db.query(User).filter(User.company_id == company.id, User.status == AccountStatus.ACTIVE).count()
        if active_count >= company.max_users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Company user limit reached: maximum {company.max_users} users allowed.",
            )

        # Verify email not taken or activate pre-provisioned inactive user
        existing_user = db.query(User).filter(User.email == invitation.email).first()
        if existing_user:
            if existing_user.status == AccountStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A user with this email is already registered and active.",
                )
            # Activate pre-provisioned inactive account
            existing_user.name = name.strip() or existing_user.name
            existing_user.password_hash = get_password_hash(password)
            existing_user.status = AccountStatus.ACTIVE
            existing_user.branch_id = invitation.branch_id
            existing_user.company_id = invitation.company_id
            user = existing_user
        else:
            # Create user
            user = User(
                company_id=invitation.company_id,
                branch_id=invitation.branch_id,
                name=name.strip(),
                email=invitation.email,
                password_hash=get_password_hash(password),
                role=invitation.invited_role,
                status=AccountStatus.ACTIVE,
                token_version=1,
                must_change_password=False,
                failed_attempts=0,
                created_at=datetime.utcnow(),
            )
            db.add(user)
            db.flush()

        # ── Module 4: Assign UserRoleAssignment ───────────────────────────────
        from app.models import UserRoleAssignment
        scope_type = "company" if invitation.invited_role == UserRole.GLOBAL_ADMIN else "branch"
        scope_id = invitation.company_id if scope_type == "company" else invitation.branch_id
        role_str = invitation.invited_role.value

        existing_assign = db.query(UserRoleAssignment).filter(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.role == role_str,
            UserRoleAssignment.scope_type == scope_type,
            UserRoleAssignment.scope_id == scope_id,
        ).first()
        if not existing_assign:
            db.add(UserRoleAssignment(
                user_id=user.id,
                role=role_str,
                scope_type=scope_type,
                scope_id=scope_id,
                created_by=invitation.invited_by,
            ))
            if role_str == "STAFF":
                db.add(UserRoleAssignment(
                    user_id=user.id,
                    role="UPLOADER",
                    scope_type=scope_type,
                    scope_id=scope_id,
                    created_by=invitation.invited_by,
                ))

        # Mark invitation accepted
        invitation.accepted_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        logger.info(
            "Invitation accepted: user_id=%d, email=%s, company_id=%d, branch_id=%d, role=%s",
            user.id,
            user.email,
            user.company_id,
            user.branch_id,
            user.role.value,
        )
        return user


invitation_service = InvitationService()
