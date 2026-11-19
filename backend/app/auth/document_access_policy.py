"""
Module 4 – Authoritative Document Access Policy.

Centralized policy layer governing all access to documents, files, thumbnails,
OCR text, history, generated PDFs, and derived invoice copies.
Enforces:
  1. Anti-enumeration: returns 404 Not Found for out-of-scope or cross-tenant objects.
  2. 30-Day cutoff for Uploaders / Staff based on server-side UTC created_at.
  3. Single-branch restriction for Uploaders.
  4. Soft-delete masking.
  5. Derived copies inherit the source document's access restrictions.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
from fastapi import HTTPException, status
from sqlalchemy.orm import Query

from app.auth.authorization import can, get_utc_now, scope_filter
from app.auth.permissions import (
    DOCUMENT_DELETE,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_REPROCESS,
    DOCUMENT_UPLOAD,
    DOCUMENT_VIEW_BRANCH,
    DOCUMENT_VIEW_COMPANY,
    DOCUMENT_VIEW_OWN,
    INVOICE_VIEW,
)
from app.context import AuthContext, MasterAdminContext
from app.models import Document, Invoice, UserRole


class DocumentAccessPolicy:
    """Authoritative document resource access control policy."""

    @staticmethod
    def verify_document_access(
        ctx: Union[AuthContext, MasterAdminContext],
        permission: str,
        document: Optional[Document],
        allow_deleted: bool = False,
    ) -> Document:
        """
        Verify access to a specific Document object.
        Returns the document if authorized, or raises HTTPException (404/403).
        """
        # Master Admin has no document access
        if isinstance(ctx, MasterAdminContext):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # 1. Company Isolation (Hard 404 on cross-company to prevent enumeration)
        if document.company_id != ctx.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # 2. Soft-delete filtering
        if not allow_deleted and document.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # 3. Check scope (branch / ownership / 30-day cutoff)
        is_company_scope = DOCUMENT_VIEW_COMPANY in ctx.permissions or ctx.is_global_admin
        is_branch_scope = DOCUMENT_VIEW_BRANCH in ctx.permissions or ctx.role == UserRole.ADMIN

        if is_company_scope:
            # Full company access
            pass
        elif is_branch_scope:
            # Restricted to assigned branch(es)
            assigned_branches = ctx.assigned_branch_ids
            if document.branch_id not in assigned_branches:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found",
                )
        else:
            # Uploader / Staff scope: own uploads only within assigned branch
            if document.branch_id != ctx.branch_id or document.uploaded_by != ctx.user_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found",
                )

            # 30-Day cutoff evaluation
            cutoff = get_utc_now() - timedelta(days=30)
            doc_created = document.created_at
            if hasattr(doc_created, "tzinfo") and doc_created.tzinfo is not None:
                doc_created = doc_created.astimezone(timezone.utc).replace(tzinfo=None)

            if doc_created < cutoff:
                # 404 Not Found to prevent leaking document existence past 30 days
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found",
                )

        # 4. Action-level permission check
        if not can(ctx, permission, document, allow_deleted=allow_deleted):
            # Known user in scope, but lacks the specific action permission (e.g. staff deleting)
            if permission == DOCUMENT_DELETE and ctx.is_staff:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Staff cannot delete documents",
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: You do not have permission to perform this action",
            )

        return document

    @staticmethod
    def verify_invoice_access(
        ctx: Union[AuthContext, MasterAdminContext],
        permission: str,
        invoice: Optional[Invoice],
    ) -> Invoice:
        """
        Verify access to an Invoice resource.
        Crucial: A derived invoice inherits its source document's access restrictions.
        """
        if isinstance(ctx, MasterAdminContext):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        # 1. Company Isolation
        if invoice.company_id != ctx.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        # 2. Soft-delete check
        if invoice.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        # 3. Scope & Access Evaluation based on Invoice Kind:
        if getattr(invoice, "kind", "copy") == "generated":
            # Outbound Sales Invoices: EXEMPT from 30-day cutoff
            is_company_scope = DOCUMENT_VIEW_COMPANY in ctx.permissions or ctx.is_global_admin
            is_branch_scope = DOCUMENT_VIEW_BRANCH in ctx.permissions or ctx.role == UserRole.ADMIN

            if is_company_scope:
                pass
            elif is_branch_scope:
                assigned_branches = ctx.assigned_branch_ids
                if invoice.branch_id not in assigned_branches:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Invoice not found",
                    )
            else:
                # Staff / Uploader scope: branch check + draft ownership check
                if invoice.branch_id != ctx.branch_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Invoice not found",
                    )
                if invoice.status == "draft" and invoice.created_by != ctx.user_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Invoice not found",
                    )
        elif invoice.document is not None:
            # Supplier Copy with attached source document: inherits source document restrictions (inc. 30-day cutoff)
            DocumentAccessPolicy.verify_document_access(ctx, permission, invoice.document)
        else:
            # Fallback direct invoice copy scope check
            is_company_scope = DOCUMENT_VIEW_COMPANY in ctx.permissions or ctx.is_global_admin
            is_branch_scope = DOCUMENT_VIEW_BRANCH in ctx.permissions or ctx.role == UserRole.ADMIN

            if is_company_scope:
                pass
            elif is_branch_scope:
                assigned_branches = ctx.assigned_branch_ids
                if invoice.branch_id not in assigned_branches:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Invoice not found",
                    )
            else:
                if invoice.branch_id != ctx.branch_id or invoice.uploaded_by != ctx.user_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Invoice not found",
                    )
                cutoff = get_utc_now() - timedelta(days=30)
                inv_created = invoice.created_at
                if hasattr(inv_created, "tzinfo") and inv_created.tzinfo is not None:
                    inv_created = inv_created.astimezone(timezone.utc).replace(tzinfo=None)
                if inv_created < cutoff:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Invoice not found",
                    )

        return invoice

    @staticmethod
    def apply_query_scope(
        ctx: Union[AuthContext, MasterAdminContext],
        query: Query,
        model: Any,
        include_deleted: bool = False,
    ) -> Query:
        """Apply authoritative scope filters to a database query."""
        return scope_filter(ctx, query, model, include_deleted=include_deleted)
