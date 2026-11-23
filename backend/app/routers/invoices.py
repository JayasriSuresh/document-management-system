import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission, requires
from app.auth.permissions import INVOICE_DOWNLOAD, INVOICE_VIEW
from app.audit import audit
from app.audit.events import (
    DOCUMENT_VIEW as AUDIT_DOCUMENT_VIEW,
    DOCUMENT_DOWNLOAD as AUDIT_DOCUMENT_DOWNLOAD,
    ObjectType,
)
from app.config import settings
from app.context import AuthContext, get_auth_context, get_auth_context_from_query
from app.database import get_db
from app.models import Invoice, Document, UserRole
from app.repositories import InvoiceRepository
from app.schemas import InvoiceOut

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def sync_stored_invoices(db: Session, auth_context: Optional[AuthContext] = None):
    """
    Backwards-compatible wrapper for invoice storage synchronization.
    Delegates to InvoiceRepository when an auth_context is present.
    """
    if auth_context:
        repo = InvoiceRepository(db, auth_context)
        repo.sync_stored_invoices()
        return

    # Fallback system sync without context
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

            existing = db.query(Invoice).filter(Invoice.document_id == doc_id).first()
            if existing:
                continue

            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                continue

            import json
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
            db.add(new_invoice)
            db.commit()
        except Exception:
            db.rollback()


@router.get("/stats")
@requires(INVOICE_VIEW)
def get_invoice_stats(
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(INVOICE_VIEW)),
):
    """Returns aggregated summary statistics for the invoices dashboard."""
    repo = InvoiceRepository(db, auth_context)
    invoices = repo.list_invoices()

    total_count = len(invoices)
    copies_count = sum(1 for inv in invoices if inv.kind == "copy")
    generated_count = sum(1 for inv in invoices if inv.kind == "generated")
    draft_count = sum(1 for inv in invoices if inv.status == "draft")
    pending_count = sum(1 for inv in invoices if inv.status == "pending_approval")
    approved_count = sum(1 for inv in invoices if inv.status in ("approved", "available"))
    cancelled_count = sum(1 for inv in invoices if inv.status == "cancelled")

    from decimal import Decimal
    total_approved = sum(
        (Decimal(str(inv.grand_total)) for inv in invoices if inv.status in ("approved", "available") and inv.grand_total is not None),
        Decimal("0.00"),
    )

    return {
        "total_count": total_count,
        "copies_count": copies_count,
        "generated_count": generated_count,
        "sales_count": generated_count,
        "draft_count": draft_count,
        "pending_approval_count": pending_count,
        "approved_count": approved_count,
        "cancelled_count": cancelled_count,
        "total_approved_amount": str(total_approved),
        "total_billed_value": str(total_approved),
    }


@router.get("", response_model=list[InvoiceOut])
@requires(INVOICE_VIEW)
def list_invoices(
    search: str = Query(default="", description="Search in invoice number, seller, buyer, or filename"),
    kind: str = Query(default="all", description="Filter by kind: all, copy, generated"),
    status: str = Query(default="all", description="Filter by status: all, draft, pending_approval, approved, cancelled, available"),
    invoice_type: str = Query(default="all", description="Filter by invoice type: all, Tax Invoice, Bill of Supply, etc."),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(INVOICE_VIEW)),
):
    repo = InvoiceRepository(db, auth_context)
    repo.sync_stored_invoices()
    invoices = repo.list_invoices(search=search, kind=kind, status=status, invoice_type=invoice_type)

    return [
        InvoiceOut(
            id=inv.id,
            document_id=inv.document_id,
            original_filename=inv.document.original_filename if inv.document else (f"Sales Invoice {inv.invoice_number or inv.id}" if inv.kind == 'generated' else f"document_{inv.document_id}"),
            invoice_number=inv.invoice_number or (f"DRAFT-{inv.id}" if inv.status == "draft" else f"INV-{inv.id:04d}"),
            invoice_date=str(inv.invoice_date) if inv.invoice_date else "",
            seller_name=inv.seller_name or "",
            seller_gstin=inv.seller_gstin or "",
            buyer_name=inv.buyer_name or "",
            buyer_gstin=inv.buyer_gstin or "",
            grand_total=str(inv.grand_total) if inv.grand_total is not None else "",
            currency=inv.currency or "INR",
            pdf_filename=inv.pdf_filename,
            file_size=inv.file_size or 0,
            created_at=inv.created_at,
            uploaded_by=inv.uploaded_by or inv.created_by,
            uploader_name=(inv.uploader.name if inv.uploader else (inv.creator.name if inv.creator else "Unknown")),
            company_id=inv.company_id,
            company_name=inv.company.name if inv.company else "",
            branch_id=inv.branch_id,
            branch_name=inv.branch.name if inv.branch else "Unknown",
            tenant_id=inv.branch_id,
            tenant_name=inv.branch.name if inv.branch else "Unknown",
            kind=inv.kind or "copy",
            status=inv.status or "available",
            taxable_amount=str(inv.taxable_amount) if inv.taxable_amount is not None else None,
            cgst_amount=str(inv.cgst_amount) if inv.cgst_amount is not None else None,
            sgst_amount=str(inv.sgst_amount) if inv.sgst_amount is not None else None,
            igst_amount=str(inv.igst_amount) if inv.igst_amount is not None else None,
            round_off=str(inv.round_off) if inv.round_off is not None else None,
            invoice_type=inv.invoice_type or "Tax Invoice",
        )
        for inv in invoices
    ]


@router.get("/{invoice_id}", response_model=InvoiceOut)
@requires(INVOICE_VIEW)
def get_invoice(
    request: Request,
    invoice_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(INVOICE_VIEW)),
):
    repo = InvoiceRepository(db, auth_context)
    inv = repo.get_invoice(invoice_id)

    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_VIEW,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.INVOICE,
        object_id=inv.id,
        metadata={"invoice_number": inv.invoice_number},
    )
    db.commit()

    return InvoiceOut(
        id=inv.id,
        document_id=inv.document_id,
        original_filename=inv.document.original_filename if inv.document else (f"Sales Invoice {inv.invoice_number or inv.id}" if inv.kind == 'generated' else f"document_{inv.document_id}"),
        invoice_number=inv.invoice_number or (f"DRAFT-{inv.id}" if inv.status == "draft" else f"INV-{inv.id:04d}"),
        invoice_date=str(inv.invoice_date) if inv.invoice_date else "",
        seller_name=inv.seller_name or "",
        seller_gstin=inv.seller_gstin or "",
        buyer_name=inv.buyer_name or "",
        buyer_gstin=inv.buyer_gstin or "",
        grand_total=str(inv.grand_total) if inv.grand_total is not None else "",
        currency=inv.currency or "INR",
        pdf_filename=inv.pdf_filename,
        file_size=inv.file_size or 0,
        created_at=inv.created_at,
        uploaded_by=inv.uploaded_by or inv.created_by,
        uploader_name=(inv.uploader.name if inv.uploader else (inv.creator.name if inv.creator else "Unknown")),
        company_id=inv.company_id,
        company_name=inv.company.name if inv.company else "",
        branch_id=inv.branch_id,
        branch_name=inv.branch.name if inv.branch else "Unknown",
        tenant_id=inv.branch_id,
        tenant_name=inv.branch.name if inv.branch else "Unknown",
        kind=inv.kind or "copy",
        status=inv.status or "available",
        taxable_amount=str(inv.taxable_amount) if inv.taxable_amount is not None else None,
        cgst_amount=str(inv.cgst_amount) if inv.cgst_amount is not None else None,
        sgst_amount=str(inv.sgst_amount) if inv.sgst_amount is not None else None,
        igst_amount=str(inv.igst_amount) if inv.igst_amount is not None else None,
        round_off=str(inv.round_off) if inv.round_off is not None else None,
        invoice_type=inv.invoice_type or "Tax Invoice",
    )


@router.get("/{invoice_id}/pdf")
@requires(INVOICE_DOWNLOAD)
def get_invoice_pdf(
    request: Request,
    invoice_id: int,
    download: bool = Query(False),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(INVOICE_DOWNLOAD)),
):
    repo = InvoiceRepository(db, auth_context)
    inv = repo.get_invoice(invoice_id)

    pdf_path = Path(settings.STORAGE_PATH) / inv.pdf_filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Invoice PDF file missing from storage")

    disp = "attachment" if download else "inline"
    clean_name = f"invoice_{inv.invoice_number.replace('/', '_')}.pdf" if inv.invoice_number else f"invoice_{inv.id}.pdf"

    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_DOWNLOAD if download else AUDIT_DOCUMENT_VIEW,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.INVOICE,
        object_id=inv.id,
        metadata={
            "invoice_number": inv.invoice_number,
            "download_format": "pdf",
        },
    )
    db.commit()

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=clean_name,
        content_disposition_type=disp,
    )
