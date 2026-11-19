"""
Invoice repository enforcing company and branch tenant scoping.
"""

import json
from pathlib import Path
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import settings
from app.context import AuthContext
from app.models import Invoice, Document, UserRole
from app.repositories.base import BaseTenantRepository


class InvoiceRepository(BaseTenantRepository[Invoice]):
    def __init__(self, db: Session, auth_context: AuthContext):
        super().__init__(Invoice, db, auth_context)

    def list_invoices(
        self,
        search: str = "",
        kind: str = "all",
        status: str = "all",
    ) -> List[Invoice]:
        """
        List invoices scoped to the current user's company and branch,
        supporting both supplier copies and outbound sales invoices.
        """
        from sqlalchemy import or_, and_
        from datetime import datetime, timedelta, timezone

        query = self.scoped_query().outerjoin(Document, Invoice.document_id == Document.id)

        # 1. Kind Filtering
        if kind == "copy":
            query = query.filter(Invoice.kind == "copy")
            query = query.filter(or_(Invoice.document_id.is_(None), Document.deleted_at.is_(None)))
        elif kind == "generated":
            query = query.filter(Invoice.kind == "generated")
        else:
            query = query.filter(
                or_(
                    Invoice.kind == "generated",
                    and_(
                        Invoice.kind == "copy",
                        or_(Invoice.document_id.is_(None), Document.deleted_at.is_(None)),
                    ),
                )
            )

        # 2. Status Filtering
        if status and status != "all":
            query = query.filter(Invoice.status == status)

        # 3. Staff / Uploader Access Rules
        if not (self.auth_context.is_global_admin or self.auth_context.role == UserRole.ADMIN):
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            # Copies must be within 30 days and owned by user
            # Generated invoices are exempt from 30 days, but drafts must be owned
            copy_cond = and_(
                Invoice.kind == "copy",
                Invoice.created_at >= cutoff,
                or_(Invoice.uploaded_by == self.auth_context.user_id, Invoice.created_by == self.auth_context.user_id),
            )
            gen_cond = and_(
                Invoice.kind == "generated",
                Invoice.branch_id == self.auth_context.branch_id,
                or_(Invoice.status != "draft", Invoice.created_by == self.auth_context.user_id),
            )
            query = query.filter(or_(copy_cond, gen_cond))

        # 4. Search Filter
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                (Invoice.invoice_number.ilike(term))
                | (Invoice.seller_name.ilike(term))
                | (Invoice.buyer_name.ilike(term))
                | (Document.original_filename.ilike(term))
            )

        return query.order_by(Invoice.created_at.desc()).all()

    def get_invoice(self, invoice_id: int) -> Invoice:
        """Fetch an invoice enforcing company and branch scoping and derived source doc inheritance."""
        from app.auth.document_access_policy import DocumentAccessPolicy
        from app.auth.permissions import INVOICE_VIEW

        inv = self.get_by_id_or_404(invoice_id)
        return DocumentAccessPolicy.verify_invoice_access(self.auth_context, INVOICE_VIEW, inv)

    def sync_stored_invoices(self) -> None:
        """
        Scans storage for any generated_invoice_<doc_id>.pdf files
        and registers them with the correct company_id and branch_id
        matching the parent document.
        """
        storage_dir = Path(settings.STORAGE_PATH)
        if not storage_dir.exists():
            return

        for pdf_file in storage_dir.glob("generated_invoice_*.pdf"):
            try:
                stem = pdf_file.stem
                parts = stem.split("_")
                if len(parts) >= 3 and parts[-1].isdigit():
                    doc_id = int(parts[-1])
                else:
                    continue

                existing = self.db.query(Invoice).filter(Invoice.document_id == doc_id).first()
                if existing:
                    continue

                doc = self.db.query(Document).filter(Document.id == doc_id).first()
                if not doc:
                    continue

                inv_data = {}
                if doc.structured_data:
                    try:
                        inv_data = json.loads(doc.structured_data)
                    except Exception:
                        pass

                seller = inv_data.get("seller") or {}
                buyer = inv_data.get("buyer") or {}
                inv = inv_data.get("invoice") or {}
                tots = inv_data.get("totals") or {}

                inv_no = inv.get("number") or inv_data.get("bill_no") or f"INV-{doc.id:04d}"
                inv_date = inv.get("date") or inv_data.get("date") or doc.created_at.strftime("%d-%b-%Y")
                seller_name = seller.get("name") or inv_data.get("branch") or "Seller"
                seller_gst = seller.get("gstin") or inv_data.get("gst_reg_no") or ""
                buyer_name = buyer.get("name") or inv_data.get("customer_name") or "Buyer"
                buyer_gst = buyer.get("gstin") or ""

                grand_total = tots.get("grand_total")
                if grand_total is None:
                    grand_total = inv_data.get("total_amount")
                grand_total_str = str(grand_total) if grand_total is not None else ""

                file_size = pdf_file.stat().st_size if pdf_file.exists() else 0

                new_invoice = Invoice(
                    document_id=doc.id,
                    company_id=doc.company_id,
                    branch_id=doc.branch_id,
                    uploaded_by=doc.uploaded_by,
                    invoice_number=inv_no,
                    invoice_date=inv_date,
                    seller_name=seller_name,
                    seller_gstin=seller_gst,
                    buyer_name=buyer_name,
                    buyer_gstin=buyer_gst,
                    grand_total=grand_total_str,
                    currency="INR",
                    pdf_filename=pdf_file.name,
                    file_size=file_size,
                    created_at=doc.created_at,
                )
                self.db.add(new_invoice)
                self.db.commit()
            except Exception:
                self.db.rollback()
