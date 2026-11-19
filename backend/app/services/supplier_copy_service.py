"""
Supplier Invoice Copy Versioning & Stale Detection Service (Module 13 Phase 6).

Preserves historical PDF versions of OCR supplier invoice copies, detects when
OCR human edits render the current PDF stale, and creates immutable new versions
without overwriting or deleting historical files.
"""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, List, Tuple, Union, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import weasyprint

from app.audit import events
from app.audit.service import audit
from app.auth.document_access_policy import DocumentAccessPolicy
from app.auth.permissions import DOCUMENT_REPROCESS, INVOICE_VIEW, INVOICE_CREATE
from app.config import settings
from app.context import AuthContext, MasterAdminContext
from app.models import Document, Invoice, SupplierInvoiceCopy


def compute_source_data_hash(structured_data: Union[str, Dict[str, Any], None]) -> Optional[str]:
    """
    Computes a deterministic canonical SHA-256 hash of document structured OCR data.
    Uses json.dumps(data, sort_keys=True) matching Phase 1/2 verification.
    """
    if not structured_data:
        return None
    try:
        if isinstance(structured_data, str):
            data = json.loads(structured_data)
        else:
            data = structured_data
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return None


def get_current_supplier_copy(db: Session, doc_id: int) -> Optional[SupplierInvoiceCopy]:
    """Fetches the currently active supplier invoice copy for a document."""
    return (
        db.query(SupplierInvoiceCopy)
        .filter(SupplierInvoiceCopy.document_id == doc_id, SupplierInvoiceCopy.is_current == True)
        .first()
    )


def check_supplier_copy_stale(db: Session, doc: Document) -> bool:
    """
    Returns True if the current supplier copy's source_data_hash differs from
    the current canonical hash of doc.structured_data.
    """
    current_copy = get_current_supplier_copy(db, doc.id)
    if not current_copy or not current_copy.source_data_hash:
        return False
    current_doc_hash = compute_source_data_hash(doc.structured_data)
    if not current_doc_hash:
        return False
    return current_copy.source_data_hash != current_doc_hash


def render_supplier_copy_pdf(doc: Document) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    Renders invoice.html via Jinja2 + WeasyPrint using doc.structured_data.
    Returns (pdf_bytes, pdf_sha256, invoice_data).
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    def inr_filter(value):
        try:
            v = float(value)
            neg = v < 0
            v = abs(v)
            integer_part, decimal_part = f"{v:.2f}".split(".")
            if len(integer_part) > 3:
                last3 = integer_part[-3:]
                rest = integer_part[:-3]
                groups = []
                while len(rest) > 2:
                    groups.append(rest[-2:])
                    rest = rest[:-2]
                if rest:
                    groups.append(rest)
                groups.reverse()
                integer_part = ",".join(groups) + "," + last3
            result = f"{integer_part}.{decimal_part}"
            return ("-" + result) if neg else result
        except (TypeError, ValueError):
            return str(value) if value is not None else ""

    def gst_fmt(value):
        try:
            return "%g" % float(value)
        except Exception:
            return str(value) if value is not None else ""

    templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["inr"] = inr_filter
    env.filters["gst_fmt"] = gst_fmt

    template = env.get_template("invoice.html")

    inv_data = {}
    if doc.structured_data:
        try:
            inv_data = json.loads(doc.structured_data)
        except Exception:
            pass

    seller = inv_data.get("seller") or {}
    buyer = inv_data.get("buyer") or {}
    inv = inv_data.get("invoice") or {}
    delivery = inv_data.get("delivery") or {}
    bank = inv_data.get("bank") or {}
    items = inv_data.get("items") or []
    tots = inv_data.get("totals") or {}

    sig_img = (
        inv_data.get("signature_image")
        or (inv_data.get("signature") or {}).get("image_data")
        or (inv_data.get("signature") or {}).get("image_url")
        or (inv_data.get("signature") if isinstance(inv_data.get("signature"), str) else None)
    )
    signer_name = ""
    if isinstance(inv_data.get("signature"), dict):
        signer_name = inv_data["signature"].get("signer_name") or ""
    if not signer_name:
        signer_name = inv_data.get("signer_name") or seller.get("name") or ""

    rendered_html = template.render(
        seller=seller,
        buyer=buyer,
        invoice=inv,
        delivery=delivery,
        bank=bank,
        items=items,
        totals=tots,
        declaration=inv_data.get("declaration") or "",
        warranty_note=inv_data.get("warranty_note") or "",
        footer=inv_data.get("footer") or [],
        signature_image=sig_img,
        signer_name=signer_name,
    )

    pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    return pdf_bytes, pdf_sha256, inv_data


def regenerate_supplier_copy(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    doc_id: int,
) -> Tuple[SupplierInvoiceCopy, Path]:
    """
    Regenerates a supplier copy as a new version:
      - Validates access policy (enforcing 30-day cutoff for staff).
      - Locks document row with FOR UPDATE.
      - Renders PDF and computes new hashes.
      - Deactivates previous current copy (is_current = FALSE) without deleting its PDF.
      - Creates new SupplierInvoiceCopy (copy_version = previous + 1).
      - Updates parent Invoice row.
      - Records audit event.
    """
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # 1. Fetch document and enforce access policy
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.company_id == ctx.company_id, Document.deleted_at.is_(None))
        .with_for_update()
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    DocumentAccessPolicy.verify_document_access(ctx, DOCUMENT_REPROCESS, doc)

    # 2. Render new PDF and compute hashes
    pdf_bytes, pdf_sha256, inv_data = render_supplier_copy_pdf(doc)
    new_source_hash = compute_source_data_hash(doc.structured_data)

    # 3. Version calculation and deactivation of previous
    current_copy = (
        db.query(SupplierInvoiceCopy)
        .filter(SupplierInvoiceCopy.document_id == doc.id, SupplierInvoiceCopy.is_current == True)
        .first()
    )

    if current_copy:
        next_version = current_copy.copy_version + 1
        current_copy.is_current = False
        current_copy.is_stale = False
    else:
        # Check highest version ever created for this document
        highest = (
            db.query(SupplierInvoiceCopy)
            .filter(SupplierInvoiceCopy.document_id == doc.id)
            .order_by(SupplierInvoiceCopy.copy_version.desc())
            .first()
        )
        next_version = (highest.copy_version + 1) if highest else 1

    # Format filename: keep original generated_invoice_{doc.id}.pdf for v1
    if next_version == 1:
        filename = f"generated_invoice_{doc.id}.pdf"
    else:
        filename = f"generated_invoice_{doc.id}_v{next_version}.pdf"

    # Save to storage (never overwriting old version)
    storage_dir = Path(settings.STORAGE_PATH)
    storage_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = storage_dir / filename
    pdf_path.write_bytes(pdf_bytes)

    # Sync to repo storage
    try:
        repo_storage = Path("./storage/documents")
        if repo_storage.resolve() != storage_dir.resolve():
            repo_storage.mkdir(parents=True, exist_ok=True)
            (repo_storage / filename).write_bytes(pdf_bytes)
    except Exception:
        pass

    # Find or create parent Invoice
    parent_invoice = db.query(Invoice).filter(Invoice.document_id == doc.id).first()
    if not parent_invoice:
        inv = inv_data.get("invoice") or {}
        seller = inv_data.get("seller") or {}
        buyer = inv_data.get("buyer") or {}
        tots = inv_data.get("totals") or {}

        inv_no = inv.get("number") or f"INV-{doc.id:04d}"
        inv_date = inv.get("date") or doc.created_at.strftime("%d-%b-%Y")
        seller_name = seller.get("name") or "Seller"
        buyer_name = buyer.get("name") or "Buyer"
        grand_total = tots.get("grand_total")
        grand_total_dec = Decimal(str(grand_total)) if grand_total is not None else Decimal("0.00")

        parent_invoice = Invoice(
            document_id=doc.id,
            company_id=doc.company_id,
            branch_id=doc.branch_id,
            uploaded_by=doc.uploaded_by,
            kind="copy",
            status="available",
            invoice_number=inv_no,
            invoice_date=doc.created_at.date(),
            seller_name=seller_name,
            seller_gstin=seller.get("gstin") or "",
            buyer_name=buyer_name,
            buyer_gstin=buyer.get("gstin") or "",
            grand_total=grand_total_dec,
            currency="INR",
            pdf_filename=filename,
            file_size=len(pdf_bytes),
        )
        db.add(parent_invoice)
        db.flush()
    else:
        parent_invoice.pdf_filename = filename
        parent_invoice.file_size = len(pdf_bytes)
        parent_invoice.status = "available"
        parent_invoice.updated_at = datetime.now(timezone.utc)

    # Create new SupplierInvoiceCopy
    new_copy = SupplierInvoiceCopy(
        invoice_id=parent_invoice.id,
        company_id=doc.company_id,
        document_id=doc.id,
        supplier_invoice_number=parent_invoice.invoice_number,
        supplier_name=parent_invoice.seller_name,
        supplier_gstin=parent_invoice.seller_gstin,
        copy_version=next_version,
        is_current=True,
        is_stale=False,
        source_data_hash=new_source_hash,
        pdf_storage_key=filename,
        pdf_sha256=pdf_sha256,
    )
    db.add(new_copy)
    db.commit()
    db.refresh(new_copy)

    audit.record_event(
        db=db,
        action=events.SUPPLIER_COPY_REGENERATED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=parent_invoice.id,
        metadata={
            "document_id": doc.id,
            "copy_version": next_version,
            "pdf_sha256": pdf_sha256,
        },
    )

    return new_copy, pdf_path


def list_supplier_copies_for_document(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    doc_id: int,
) -> List[SupplierInvoiceCopy]:
    """Lists all versions of supplier invoice copies for a document."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.company_id == ctx.company_id, Document.deleted_at.is_(None))
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    DocumentAccessPolicy.verify_document_access(ctx, INVOICE_VIEW, doc)

    return (
        db.query(SupplierInvoiceCopy)
        .filter(SupplierInvoiceCopy.document_id == doc.id)
        .order_by(SupplierInvoiceCopy.copy_version.desc())
        .all()
    )
