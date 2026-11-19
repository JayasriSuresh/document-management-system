"""
Module 5 – Centralized Audit Service.

Provides audit.record() and helpers to ensure:
  1. Business action and audit log commit atomically within the same transaction.
  2. Failed authentication events are reliably recorded via a separate transaction.
  3. Sensitive metadata is automatically sanitized before storage.
  4. Master Admin actions are clearly separated from company user actions.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, Union
from fastapi import Request
from sqlalchemy.orm import Session

from app.audit.events import ActorType
from app.audit.sanitizer import sanitize_metadata
from app.context import AuthContext, MasterAdminContext
from app.database import SessionLocal
from app.middleware import get_request_id

logger = logging.getLogger("dms.audit")

TRUSTED_PROXIES = {"127.0.0.1", "::1", "localhost"}


def extract_client_ip(request: Optional[Request]) -> Optional[str]:
    """Extract client IP, honoring X-Forwarded-For only from trusted proxies."""
    if not request:
        return None

    client_host = request.client.host if request.client else None
    if client_host in TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First IP in comma-separated list is the original client
            return forwarded.split(",")[0].strip()

    return client_host


def extract_user_agent(request: Optional[Request]) -> Optional[str]:
    """Extract and truncate user agent header."""
    if not request:
        return None
    ua = request.headers.get("User-Agent")
    return ua[:512] if ua else None


class AuditService:
    """Centralized, tamper-resistant audit recording service."""

    def record(
        self,
        db: Session,
        action: str,
        actor_type: Union[ActorType, str],
        actor_id: Optional[int] = None,
        company_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        object_type: Optional[str] = None,
        object_id: Optional[Union[str, int]] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        occurred_at: Optional[datetime] = None,
    ):
        """
        Record a security-relevant action in the database.
        Crucial: Operates inside the caller's database transaction.
        Does NOT independently commit, guaranteeing atomic commit/rollback.
        """
        from app.models import AuditLog

        # Ensure UTC datetime
        if occurred_at is None:
            occurred_at = datetime.now(timezone.utc)
        elif occurred_at.tzinfo is not None:
            occurred_at = occurred_at.astimezone(timezone.utc)

        # Sanitize metadata against allowlist
        clean_metadata = sanitize_metadata(metadata)

        # Ensure actor_type is string value
        actor_type_val = actor_type.value if hasattr(actor_type, "value") else str(actor_type)

        audit_entry = AuditLog(
            occurred_at=occurred_at,
            actor_type=actor_type_val,
            actor_id=actor_id,
            company_id=company_id,
            branch_id=branch_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id or get_request_id(),
            event_metadata=clean_metadata,
        )

        db.add(audit_entry)
        db.flush()  # Validates constraints and assigns ID within transaction
        return audit_entry

    def record_event(
        self,
        db: Session,
        action: str,
        request: Optional[Request] = None,
        ctx: Optional[Union[AuthContext, MasterAdminContext, Any]] = None,
        auth_context: Optional[Union[AuthContext, MasterAdminContext, Any]] = None,
        object_type: Optional[str] = None,
        object_id: Optional[Union[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        company_id: Optional[int] = None,
        branch_id: Optional[int] = None,
    ):
        """
        Convenience wrapper that automatically extracts actor and request context.
        Operates inside the caller's database transaction.
        """
        target_ctx = ctx or auth_context
        actor_type = ActorType.ANONYMOUS
        actor_id = None
        eff_company_id = company_id
        eff_branch_id = branch_id

        if isinstance(target_ctx, MasterAdminContext):
            actor_type = ActorType.MASTER_ADMIN
            actor_id = target_ctx.admin_id
            # For Master Admin, company_id represents the target company being acted upon
        elif isinstance(target_ctx, AuthContext):
            actor_type = ActorType.COMPANY_USER
            actor_id = target_ctx.user_id
            if eff_company_id is None:
                eff_company_id = target_ctx.company_id
            if eff_branch_id is None:
                eff_branch_id = target_ctx.branch_id
        elif target_ctx is not None and hasattr(target_ctx, "id"):
            actor_type = ActorType.COMPANY_USER
            actor_id = getattr(target_ctx, "id", None)
            if eff_company_id is None:
                eff_company_id = getattr(target_ctx, "company_id", None)
            if eff_branch_id is None:
                eff_branch_id = getattr(target_ctx, "branch_id", None)
            # Legacy User fallback
            actor_type = ActorType.COMPANY_USER
            actor_id = ctx.id
            if eff_company_id is None:
                eff_company_id = getattr(ctx, "company_id", None)
            if eff_branch_id is None:
                eff_branch_id = getattr(ctx, "branch_id", None)

        ip = extract_client_ip(request)
        ua = extract_user_agent(request)
        req_id = get_request_id()

        return self.record(
            db=db,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            company_id=eff_company_id,
            branch_id=eff_branch_id,
            object_type=object_type,
            object_id=object_id,
            ip=ip,
            user_agent=ua,
            request_id=req_id,
            metadata=metadata,
        )

    def record_auth_failure(
        self,
        action: str,
        email: Optional[str] = None,
        reason: Optional[str] = None,
        request: Optional[Request] = None,
        actor_type: Union[ActorType, str] = ActorType.ANONYMOUS,
        company_id: Optional[int] = None,
    ):
        """
        Special separate-transaction handler for failed authentication attempts.
        Ensures failed logins are permanently recorded even when the calling
        business route aborts or rolls back with HTTP 401/403.
        """
        meta = {}
        if email:
            meta["email"] = email
        if reason:
            meta["reason"] = reason

        ip = extract_client_ip(request)
        ua = extract_user_agent(request)
        req_id = get_request_id()

        # Execute in an isolated transaction so it is never rolled back
        with SessionLocal() as auth_db:
            try:
                self.record(
                    db=auth_db,
                    action=action,
                    actor_type=actor_type,
                    actor_id=None,
                    company_id=company_id,
                    branch_id=None,
                    object_type="user",
                    object_id=None,
                    ip=ip,
                    user_agent=ua,
                    request_id=req_id,
                    metadata=meta,
                )
                auth_db.commit()
            except Exception as e:
                auth_db.rollback()
                logger.error(f"Failed to record auth failure event: {e}")


# Singleton instance for application-wide use
audit = AuditService()
