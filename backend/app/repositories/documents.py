"""
Document repository enforcing company and branch tenant scoping.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.context import AuthContext
from app.models import Document, OcrStatus, UserRole
from app.repositories.base import BaseTenantRepository


class DocumentRepository(BaseTenantRepository[Document]):
    def __init__(self, db: Session, auth_context: AuthContext):
        super().__init__(Document, db, auth_context)

    def list_documents(self, search: str = "", branch_id: Optional[int] = None) -> List[Document]:
        """
        List documents with company + branch scoping, soft-delete exclusion,
        optional branch filter for Company Admins, and optional ILIKE search over ocr_text or original_filename.
        """
        query = self.scoped_query()

        if branch_id is not None and (self.auth_context.is_global_admin or "document.view_company" in self.auth_context.permissions):
            query = query.filter(Document.branch_id == branch_id)

        if search:
            query = query.filter(
                (Document.ocr_text.ilike(f"%{search}%"))
                | (Document.original_filename.ilike(f"%{search}%"))
            )

        return query.order_by(Document.created_at.desc()).all()

    def get_document(self, doc_id: int) -> Document:
        """Fetch single document enforcing company and branch scope (returns 404 if out-of-scope)."""
        from app.auth.document_access_policy import DocumentAccessPolicy
        from app.auth.permissions import DOCUMENT_VIEW_OWN

        doc = self.get_by_id_or_404(doc_id)
        return DocumentAccessPolicy.verify_document_access(self.auth_context, DOCUMENT_VIEW_OWN, doc)

    def create_document(
        self,
        original_filename: str,
        storage_key: str,
        mime_type: str,
        file_size: int,
        sha256: Optional[str] = None,
        page_count: Optional[int] = None,
        error_code: Optional[str] = None,
        commit: bool = True,
    ) -> Document:
        """
        Create a document with company_id and branch_id derived strictly
        from the trusted AuthContext.
        """
        self.auth_context.assert_active_company()

        # Enforce that documents cannot be uploaded to a deactivated branch
        from app.models import Branch
        target_branch = self.db.query(Branch).filter(Branch.id == self.auth_context.branch_id).first()
        if target_branch and (target_branch.status or "active").lower() == "inactive":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot upload documents to deactivated branch '{target_branch.name}'.",
            )

        doc = Document(
            company_id=self.auth_context.company_id,
            branch_id=self.auth_context.branch_id,
            uploaded_by=self.auth_context.user_id,
            original_filename=original_filename,
            storage_key=storage_key,
            mime_type=mime_type,
            file_size=file_size,
            sha256=sha256,
            page_count=page_count,
            error_code=error_code,
            ocr_status=OcrStatus.UPLOADED,
        )
        self.db.add(doc)
        if commit:
            self.db.commit()
            self.db.refresh(doc)
        else:
            self.db.flush()
        return doc

    def restore_document(self, doc_id: int, commit: bool = True) -> Document:
        """
        Restore a soft-deleted document.
        - Verifies company is active
        - Verifies user has permission to restore
        - Verifies physical file still exists in storage
        - Verifies no active document with same SHA-256 exists in company
        - Sets restored_at and restored_by
        """
        self.auth_context.assert_active_company()

        from app.storage import get_storage_adapter
        from app.auth.document_access_policy import DocumentAccessPolicy
        from app.auth.permissions import DOCUMENT_DELETE

        # Fetch soft-deleted record
        doc = self.get_by_id_or_404(doc_id, include_deleted=True)
        if doc.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is not deleted.",
            )

        # Enforce authorization using same permission governing deletion
        DocumentAccessPolicy.verify_document_access(self.auth_context, DOCUMENT_DELETE, doc, allow_deleted=True)

        # 1. Verify physical file exists in storage
        storage = get_storage_adapter()
        if not storage.exists(doc.storage_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Original file is missing from storage and cannot be restored.",
            )

        # 2. Check for duplicate conflict with active documents in the company
        if doc.sha256:
            active_dup = (
                self.db.query(Document)
                .filter(
                    Document.company_id == doc.company_id,
                    Document.sha256 == doc.sha256,
                    Document.deleted_at.is_(None),
                    Document.id != doc.id,
                )
                .first()
            )
            if active_dup:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot restore document: an active document with identical content (SHA-256) already exists in this company.",
                )

        # 3. Restore
        doc.deleted_at = None
        doc.deleted_by = None
        doc.restored_at = datetime.utcnow()
        doc.restored_by = self.auth_context.user_id

        if commit:
            self.db.commit()
            self.db.refresh(doc)
        else:
            self.db.flush()
        return doc

    def list_documents_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        status_filter: Optional[str] = None,
        branch_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        include_deleted: bool = False,
    ):
        """
        Server-side paginated document query enforcing tenant scoping and filtering.
        Returns (items, total_count, page, page_size, total_pages).
        """
        query = self.scoped_query(include_deleted=include_deleted)

        if include_deleted:
            query = query.filter(Document.deleted_at.isnot(None))

        # Branch filter
        if branch_id is not None:
            if self.auth_context.is_global_admin or branch_id in self.auth_context.assigned_branch_ids:
                query = query.filter(Document.branch_id == branch_id)
            else:
                # Return empty query if filtering by unassigned branch
                query = query.filter(Document.id == -1)

        # Status filter
        if status_filter:
            norm_status = status_filter.upper()
            query = query.filter(Document.ocr_status == norm_status)

        # Date range filters
        if date_from:
            query = query.filter(Document.created_at >= date_from)
        if date_to:
            query = query.filter(Document.created_at <= date_to)

        # Search filter
        if search:
            query = query.filter(
                (Document.ocr_text.ilike(f"%{search}%"))
                | (Document.original_filename.ilike(f"%{search}%"))
            )

        total_count = query.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        items = (
            query.order_by(Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total_count, page, page_size, total_pages

    def delete_document(self, doc_id: int, commit: bool = True) -> Document:
        """
        Soft delete a document.
        Staff role is forbidden (HTTP 403).
        Admins can only delete within their company and branch.
        """
        self.auth_context.assert_active_company()

        # Enforce that documents cannot be uploaded to a deactivated branch
        from app.models import Branch
        target_branch = self.db.query(Branch).filter(Branch.id == self.auth_context.branch_id).first()
        if target_branch and (target_branch.status or "active").lower() == "inactive":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot upload documents to deactivated branch '{target_branch.name}'.",
            )
        from app.auth.document_access_policy import DocumentAccessPolicy
        from app.auth.permissions import DOCUMENT_DELETE

        doc = self.get_by_id_or_404(doc_id)
        DocumentAccessPolicy.verify_document_access(self.auth_context, DOCUMENT_DELETE, doc)

        doc.deleted_at = datetime.utcnow()
        doc.deleted_by = self.auth_context.user_id
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return doc

    def reprocess_document(self, doc_id: int, commit: bool = True) -> Document:
        """Reset document OCR state for reprocessing."""
        self.auth_context.assert_active_company()

        # Enforce that documents cannot be uploaded to a deactivated branch
        from app.models import Branch
        target_branch = self.db.query(Branch).filter(Branch.id == self.auth_context.branch_id).first()
        if target_branch and (target_branch.status or "active").lower() == "inactive":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot upload documents to deactivated branch '{target_branch.name}'.",
            )
        from app.auth.document_access_policy import DocumentAccessPolicy
        from app.auth.permissions import DOCUMENT_REPROCESS

        doc = self.get_by_id_or_404(doc_id)
        DocumentAccessPolicy.verify_document_access(self.auth_context, DOCUMENT_REPROCESS, doc)

        doc.ocr_status = OcrStatus.UPLOADED
        doc.ocr_text = None
        if commit:
            self.db.commit()
            self.db.refresh(doc)
        else:
            self.db.flush()
        return doc
        return doc
