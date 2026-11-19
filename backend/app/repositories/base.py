"""
Base repository for tenant-scoped data access in DMS.

Guarantees:
  1. Every query automatically filters by auth_context.company_id (mandatory for tenant operations).
  2. Branch-level isolation is applied according to user role:
     - GLOBAL_ADMIN: Can access all branches within their company.
     - ADMIN: Restricted to their assigned branch within the company.
     - STAFF: Restricted to their assigned branch and their own uploads within the 30-day window.
  3. Soft-deleted records are automatically filtered out unless specifically requested.
  4. Cross-company access is strictly impossible at the query layer.
"""

from datetime import datetime, timedelta
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session, Query
from fastapi import HTTPException, status

from app.context import AuthContext
from app.models import UserRole

T = TypeVar("T")


class BaseTenantRepository(Generic[T]):
    """
    Base repository enforcing mandatory company scoping and role-based branch filtering.
    """

    def __init__(self, model: Type[T], db: Session, auth_context: AuthContext):
        self.model = model
        self.db = db
        self.auth_context = auth_context

    def _base_query(self, include_deleted: bool = False) -> Query:
        """
        Builds the baseline query with mandatory company filtering and soft-delete exclusion.
        """
        query = self.db.query(self.model)

        # 1. Mandatory Company Isolation
        # Unless GLOBAL_ADMIN explicitly operating in global cross-company mode (if supported),
        # all queries are hard-scoped to auth_context.company_id.
        if hasattr(self.model, "company_id"):
            query = query.filter(self.model.company_id == self.auth_context.company_id)

        # 2. Soft-delete filter
        if hasattr(self.model, "deleted_at") and not include_deleted:
            query = query.filter(self.model.deleted_at.is_(None))

        return query

    def scoped_query(self, include_deleted: bool = False) -> Query:
        """
        Builds fully-scoped query incorporating Company Scope + Branch Scope + 30-day Staff restrictions
        via the authoritative DocumentAccessPolicy.
        """
        from app.auth.document_access_policy import DocumentAccessPolicy

        base = self.db.query(self.model)
        return DocumentAccessPolicy.apply_query_scope(
            self.auth_context,
            base,
            self.model,
            include_deleted=include_deleted,
        )

    def get_by_id_or_404(self, record_id: int, include_deleted: bool = False) -> T:
        """
        Fetch a single record by ID enforcing company and branch isolation.
        Returns 404 for out-of-scope records to avoid revealing resource existence.
        """
        record = self.scoped_query(include_deleted=include_deleted).filter(self.model.id == record_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} not found",
            )
        return record
