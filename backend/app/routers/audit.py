"""
Module 5 – Audit Log Read APIs.

Provides:
  - GET /api/audit        (Tenant Audit Logs: Company Admin & Branch Admin scoped)
  - GET /api/admin/audit  (Platform Audit Logs: Master Admin platform-wide view)
"""

from datetime import datetime
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission, requires
from app.auth.permissions import (
    AUDIT_VIEW_BRANCH,
    AUDIT_VIEW_COMPANY,
    AUDIT_VIEW_PLATFORM,
    PLATFORM_MANAGE,
)
from app.context import AuthContext, MasterAdminContext, require_portal
from app.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogOut, AuditLogPaginationResponse

router = APIRouter(tags=["audit"])


@router.get("/api/audit", response_model=AuditLogPaginationResponse)
@requires(AUDIT_VIEW_BRANCH)
def get_tenant_audit_logs(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page (max 100)"),
    start_date: Optional[datetime] = Query(default=None, description="Filter logs after this UTC datetime"),
    end_date: Optional[datetime] = Query(default=None, description="Filter logs before this UTC datetime"),
    action: Optional[str] = Query(default=None, description="Filter by exact action string"),
    actor_type: Optional[str] = Query(default=None, description="Filter by actor type"),
    actor_id: Optional[int] = Query(default=None, description="Filter by actor ID"),
    object_type: Optional[str] = Query(default=None, description="Filter by object type"),
    object_id: Optional[str] = Query(default=None, description="Filter by object ID"),
    branch_id: Optional[int] = Query(default=None, description="Filter by branch ID"),
    db: Session = Depends(get_db),
    auth_ctx: AuthContext = Depends(require_permission(AUDIT_VIEW_BRANCH)),
):
    """
    Retrieve audit logs for the authenticated tenant company.
    - Company Admins (with audit.view_company) can view company-wide logs across all branches.
    - Branch Admins (with audit.view_branch) are strictly scoped to their assigned branch.
    - Uploaders and Staff have no audit access.
    """
    auth_ctx.assert_active_company()

    query = db.query(AuditLog).filter(AuditLog.company_id == auth_ctx.company_id)

    has_company_scope = (
        AUDIT_VIEW_COMPANY in auth_ctx.permissions or auth_ctx.is_global_admin
    )

    if has_company_scope:
        if branch_id is not None:
            query = query.filter(AuditLog.branch_id == branch_id)
    else:
        # Branch-scoped user: strictly restrict to user's assigned branch
        if branch_id is not None and branch_id != auth_ctx.branch_id:
            # Return 404 anti-enumeration for unauthorized branch filter
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Branch not found",
            )
        query = query.filter(AuditLog.branch_id == auth_ctx.branch_id)

    # Date range filters
    if start_date:
        query = query.filter(AuditLog.occurred_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.occurred_at <= end_date)

    # Attribute filters
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_type:
        query = query.filter(AuditLog.actor_type == actor_type)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if object_type:
        query = query.filter(AuditLog.object_type == object_type)
    if object_id is not None:
        query = query.filter(AuditLog.object_id == str(object_id))

    total = query.count()
    pages = math.ceil(total / page_size) if total > 0 else 1

    records = (
        query.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [AuditLogOut.model_validate(r) for r in records]

    return AuditLogPaginationResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_count=total,
        total_pages=pages,
    )


@router.get("/api/admin/audit", response_model=AuditLogPaginationResponse)
@requires(PLATFORM_MANAGE)
def get_platform_audit_logs(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page (max 100)"),
    company_id: Optional[int] = Query(default=None, description="Filter by company ID"),
    actor_type: Optional[str] = Query(default=None, description="Filter by actor type"),
    action: Optional[str] = Query(default=None, description="Filter by exact action string"),
    object_type: Optional[str] = Query(default=None, description="Filter by object type"),
    start_date: Optional[datetime] = Query(default=None, description="Filter logs after this UTC datetime"),
    end_date: Optional[datetime] = Query(default=None, description="Filter logs before this UTC datetime"),
    search: Optional[str] = Query(default=None, description="Search in action or object_id"),
    db: Session = Depends(get_db),
    admin_ctx: MasterAdminContext = Depends(require_permission(PLATFORM_MANAGE)),
):
    """
    Platform-level audit log retrieval for Master Administrators.
    Can inspect platform-wide events or drill down into specific companies.
    """
    query = db.query(AuditLog)

    if company_id is not None:
        query = query.filter(AuditLog.company_id == company_id)

    if actor_type:
        query = query.filter(AuditLog.actor_type == actor_type)

    if action:
        query = query.filter(AuditLog.action == action)

    if object_type:
        query = query.filter(AuditLog.object_type == object_type)

    if start_date:
        query = query.filter(AuditLog.occurred_at >= start_date)

    if end_date:
        query = query.filter(AuditLog.occurred_at <= end_date)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (AuditLog.action.ilike(search_pattern))
            | (AuditLog.object_id.ilike(search_pattern))
            | (AuditLog.ip.ilike(search_pattern))
        )

    total = query.count()
    pages = math.ceil(total / page_size) if total > 0 else 1

    records = (
        query.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [AuditLogOut.model_validate(r) for r in records]

    return AuditLogPaginationResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_count=total,
        total_pages=pages,
    )
