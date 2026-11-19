"""
Module 4 – Centralized Authorization Engine.

Provides the single authoritative policy layer:
  - can(ctx, permission, resource=None) -> bool
  - scope_filter(ctx, query, model, include_deleted=False) -> Query
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Set, Union
from sqlalchemy.orm import Query
from sqlalchemy import text

from app.auth.permissions import (
    DOCUMENT_DELETE,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_REPROCESS,
    DOCUMENT_UPLOAD,
    DOCUMENT_VIEW_BRANCH,
    DOCUMENT_VIEW_COMPANY,
    DOCUMENT_VIEW_OWN,
    INVOICE_DOWNLOAD,
    INVOICE_VIEW,
    AUDIT_VIEW_PLATFORM,
    PLATFORM_MANAGE,
    is_valid_permission,
)
from app.auth.role_permissions import (
    ROLE_ADMIN,
    ROLE_GLOBAL_ADMIN,
    ROLE_MASTER_ADMIN,
    ROLE_STAFF,
    ROLE_UPLOADER,
    get_permissions_for_role,
)
from app.context import AuthContext, MasterAdminContext
from app.models import AccountStatus, CompanyStatus


def get_utc_now() -> datetime:
    """Return timezone-aware or naive UTC datetime consistently."""
    return datetime.utcnow()


get_current_utc = get_utc_now


def can(
    ctx: Union[AuthContext, MasterAdminContext, Any],
    permission: str,
    resource: Optional[Any] = None,
    allow_deleted: bool = False,
) -> bool:
    """
    Authoritative permission check.
    Answers: Is this user allowed to perform this action (optionally on this resource)?
    
    Fail-closed: returns False for unknown permissions, inactive accounts,
    mismatched companies/branches, soft-deleted documents, or expired 30-day windows.
    """
    if not is_valid_permission(permission):
        return False

    # 1. Master Admin (Platform Root Identity)
    if isinstance(ctx, MasterAdminContext):
        if ctx.status != AccountStatus.ACTIVE:
            return False
        # Master Admin holds platform-level administrative and security permissions
        master_perms = get_permissions_for_role(ROLE_MASTER_ADMIN)
        return permission in master_perms and resource is None

    # 2. Tenant AuthContext validation
    if not isinstance(ctx, AuthContext):
        return False

    if ctx.status != AccountStatus.ACTIVE:
        return False

    # Block suspended companies completely
    if ctx.company_status == CompanyStatus.SUSPENDED:
        return False

    # Check permission in user's effective permissions
    if permission not in ctx.permissions:
        return False

    # If no resource provided, action-level check passed
    if resource is None:
        return True

    # 3. Resource-level authorization
    # Resource MUST have company_id and match user's company
    res_company_id = getattr(resource, "company_id", None)
    if res_company_id is None or res_company_id != ctx.company_id:
        return False

    # Soft-deleted check (unless explicitly allowed, e.g. for restore operations)
    res_deleted_at = getattr(resource, "deleted_at", None)
    if res_deleted_at is not None and not allow_deleted:
        return False

    res_branch_id = getattr(resource, "branch_id", None)
    res_uploaded_by = getattr(resource, "uploaded_by", None)
    res_created_at = getattr(resource, "created_at", None)

    # ── Company-Wide Scope ───────────────────────────────────────────────────
    # If user has document.view_company, they can access resources across any branch in their company
    if DOCUMENT_VIEW_COMPANY in ctx.permissions or ctx.is_global_admin:
        return True

    # ── Branch-Level Scope ───────────────────────────────────────────────────
    # If user has document.view_branch, resource must be in their assigned branch(es)
    if DOCUMENT_VIEW_BRANCH in ctx.permissions or ctx.role == ROLE_ADMIN:
        assigned_branches = ctx.assigned_branch_ids
        if res_branch_id is not None and res_branch_id not in assigned_branches:
            return False
        return True

    # ── Own-Document Scope (Uploader / Staff 30-Day Policy) ───────────────────
    # Restricted to: same company + same branch + own uploads + uploaded within 30 days
    if DOCUMENT_VIEW_OWN in ctx.permissions or ctx.role in (ROLE_STAFF, ROLE_UPLOADER):
        # 1. Branch check
        if res_branch_id is not None and res_branch_id != ctx.branch_id:
            return False

        # 2. Ownership check
        if res_uploaded_by is not None and res_uploaded_by != ctx.user_id:
            return False

        # 3. 30-day cutoff check using UTC
        if res_created_at is not None:
            # Handle both naive and aware UTC datetimes safely
            now_utc = get_utc_now()
            cutoff = now_utc - timedelta(days=30)
            
            check_time = res_created_at
            if hasattr(check_time, "tzinfo") and check_time.tzinfo is not None:
                check_time = check_time.astimezone(timezone.utc).replace(tzinfo=None)

            if check_time < cutoff:
                return False

        return True

    # Default deny
    return False


def scope_filter(
    ctx: Union[AuthContext, MasterAdminContext, Any],
    query: Query,
    model: Any,
    include_deleted: bool = False,
) -> Query:
    """
    Applies authoritative SQL filters to restrict queries before returning records.
    Enforces Company Scope, Branch Scope, Ownership, and the 30-day Uploader policy.
    """
    # Master Admin has no access to tenant documents/invoices
    if isinstance(ctx, MasterAdminContext):
        return query.filter(text("1=0"))

    if not isinstance(ctx, AuthContext):
        return query.filter(text("1=0"))

    # 1. Mandatory Company Isolation
    if hasattr(model, "company_id"):
        query = query.filter(model.company_id == ctx.company_id)

    # 2. Soft-delete filter
    if hasattr(model, "deleted_at") and not include_deleted:
        query = query.filter(model.deleted_at.is_(None))

    # 3. Company-Wide Scope
    if DOCUMENT_VIEW_COMPANY in ctx.permissions or ctx.is_global_admin:
        return query

    # 4. Branch-Level Scope (ADMIN)
    if DOCUMENT_VIEW_BRANCH in ctx.permissions or ctx.role == ROLE_ADMIN:
        if hasattr(model, "branch_id"):
            assigned_branches = ctx.assigned_branch_ids
            query = query.filter(model.branch_id.in_(assigned_branches))
        return query

    # 5. Own-Document Scope (UPLOADER / STAFF)
    if DOCUMENT_VIEW_OWN in ctx.permissions or ctx.role in (ROLE_STAFF, ROLE_UPLOADER):
        if hasattr(model, "branch_id"):
            query = query.filter(model.branch_id == ctx.branch_id)
        if hasattr(model, "uploaded_by"):
            query = query.filter(model.uploaded_by == ctx.user_id)
        if hasattr(model, "created_at"):
            cutoff = get_utc_now() - timedelta(days=30)
            query = query.filter(model.created_at >= cutoff)
        return query

    # Fail closed
    return query.filter(text("1=0"))
