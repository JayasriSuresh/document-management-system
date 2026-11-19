"""
Outbound Sales Invoices Router (Module 13).
Handles draft lifecycle, deterministic tax engine preview, submission, approval, issuance, and cancellation.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
from pathlib import Path
import secrets
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Response
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from sqlalchemy.orm import Session
import fitz

from app.config import settings
from app.storage import get_storage_adapter

from app.audit import events
from app.audit.service import audit
from app.auth.authorization import can
from app.auth.dependencies import require_permission, requires
from app.auth.document_access_policy import DocumentAccessPolicy
from app.auth.permissions import (
    INVOICE_SALES_CREATE,
    INVOICE_SALES_EDIT,
    INVOICE_SALES_DISCARD,
    INVOICE_SALES_SUBMIT,
    INVOICE_SALES_APPROVE,
    INVOICE_SALES_CANCEL,
    INVOICE_SALES_VIEW,
)
from app.context import AuthContext, MasterAdminContext, get_auth_context, get_auth_context_from_query
from app.database import get_db
from app.models import Invoice, OutboundSalesInvoice, InvoiceItem, User, SalesInvoiceSignature, TemporarySignatureUpload
from app.schemas import (
    SalesInvoiceDraftCreate,
    SalesInvoiceDraftUpdate,
    SalesInvoiceApprovalInput,
    SalesInvoiceCancelInput,
    SalesInvoiceOut,
    InvoiceItemOut,
    TaxPreviewRequest,
    TaxPreviewResponse,
    SignatureLayoutOut,
    TemporarySignatureUploadOut,
)
from app.services.gstin_validator import INDIAN_GST_STATE_CODES
from app.services.invoice_issuance import (
    create_sales_invoice_draft,
    update_sales_invoice_draft,
    discard_sales_invoice_draft,
    submit_sales_invoice_for_approval,
    approve_and_issue_sales_invoice,
    reject_sales_invoice,
    cancel_sales_invoice,
    render_draft_sales_invoice_pdf_bytes,
)
from app.services.tax_engine import (
    calculate_taxes,
    TaxLineInput,
    GstClassification,
)

router = APIRouter(prefix="/api/sales-invoices", tags=["sales_invoices"])


def _build_sales_invoice_out(db: Session, invoice: Invoice) -> SalesInvoiceOut:
    sales = invoice.sales_detail
    if not sales:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sales invoice details missing")

    customer = sales.customer
    gst_reg = sales.gst_registration

    billing_addr_dict = None
    if sales.billing_address:
        b = sales.billing_address
        billing_addr_dict = {
            "id": b.id,
            "address_line1": b.address_line1,
            "address_line2": b.address_line2,
            "city": b.city,
            "state_code": b.state_code,
            "state_name": b.state_name,
            "pincode": b.pincode,
        }

    shipping_addr_dict = None
    if sales.shipping_address:
        s = sales.shipping_address
        shipping_addr_dict = {
            "id": s.id,
            "address_line1": s.address_line1,
            "address_line2": s.address_line2,
            "city": s.city,
            "state_code": s.state_code,
            "state_name": s.state_name,
            "pincode": s.pincode,
        }

    creator_name = None
    if invoice.created_by:
        creator = db.query(User).filter(User.id == invoice.created_by).first()
        if creator:
            creator_name = creator.name

    approver_name = None
    if sales.approved_by:
        approver = db.query(User).filter(User.id == sales.approved_by).first()
        if approver:
            approver_name = approver.name

    sorted_items = sorted(invoice.items, key=lambda x: x.item_order)
    items_out = [
        InvoiceItemOut(
            id=item.id,
            item_order=item.item_order,
            description=item.description,
            hsn_sac_code=item.hsn_sac_code,
            item_type=item.item_type,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=item.unit_price,
            gross_amount=item.gross_amount,
            discount_percent=item.discount_percent,
            discount_amount=item.discount_amount,
            taxable_amount=item.taxable_amount,
            gst_classification=item.gst_classification,
            gst_rate=item.gst_rate,
            cgst_rate=item.cgst_rate,
            cgst_amount=item.cgst_amount,
            sgst_rate=item.sgst_rate,
            sgst_amount=item.sgst_amount,
            igst_rate=item.igst_rate,
            igst_amount=item.igst_amount,
            total_tax_amount=item.total_tax_amount,
            line_total=item.line_total,
        )
        for item in sorted_items
    ]

    branch_name = invoice.branch.name if invoice.branch else None
    pos_state_name = INDIAN_GST_STATE_CODES.get(str(sales.place_of_supply).strip().zfill(2), sales.place_of_supply)

    sigs_out = [
        SignatureLayoutOut(
            id=s.id,
            invoice_id=s.invoice_id,
            storage_key=s.storage_key,
            original_filename=s.original_filename,
            mime_type=s.mime_type,
            file_size=s.file_size,
            sha256=s.sha256,
            page_number=s.page_number,
            is_pinned_to_last_page=s.is_pinned_to_last_page,
            x_mm=s.x_mm,
            y_mm=s.y_mm,
            width_mm=s.width_mm,
            height_mm=s.height_mm,
            image_url=f"/api/sales-invoices/signatures/{s.id}/image",
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in (invoice.signatures or [])
    ]

    return SalesInvoiceOut(
        id=invoice.id,
        company_id=invoice.company_id,
        branch_id=invoice.branch_id,
        branch_name=branch_name,
        kind=invoice.kind,
        status=invoice.status,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        financial_year=invoice.financial_year,
        customer_id=customer.id if customer else 0,
        customer_name=customer.name if customer else invoice.buyer_name or "",
        customer_gstin=customer.gstin if customer else invoice.buyer_gstin,
        is_b2c=customer.is_b2c if customer else True,
        gst_registration_id=gst_reg.id if gst_reg else 0,
        supplier_gstin=gst_reg.gstin if gst_reg else invoice.seller_gstin or "",
        supplier_legal_name=gst_reg.legal_name if gst_reg else invoice.seller_name or "",
        place_of_supply=sales.place_of_supply,
        place_of_supply_state_name=pos_state_name,
        billing_address=billing_addr_dict,
        shipping_address=shipping_addr_dict,
        taxable_amount=invoice.taxable_amount or Decimal("0.00"),
        cgst_amount=invoice.cgst_amount or Decimal("0.00"),
        sgst_amount=invoice.sgst_amount or Decimal("0.00"),
        igst_amount=invoice.igst_amount or Decimal("0.00"),
        round_off=invoice.round_off or Decimal("0.00"),
        grand_total=invoice.grand_total or Decimal("0.00"),
        currency=invoice.currency or "INR",
        notes=invoice.notes,
        terms_and_conditions=None,
        pdf_filename=invoice.pdf_filename,
        pdf_sha256=sales.pdf_sha256,
        created_by=invoice.created_by,
        created_by_name=creator_name,
        approved_by=sales.approved_by,
        approved_by_name=approver_name,
        approved_at=sales.approved_at,
        issued_at=sales.pdf_generated_at,
        items=items_out,
        signatures=sigs_out,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


@router.post("/preview-tax", response_model=TaxPreviewResponse)
@requires(INVOICE_SALES_CREATE)
def preview_tax(
    data: TaxPreviewRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """
    Simulates pure-Decimal GST tax calculation without persisting anything to the database.
    Useful for interactive frontend line item entry.
    """
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    tax_inputs = [
        TaxLineInput(
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            hsn_sac_code=item.hsn_sac_code,
            item_type=item.item_type,
            unit=item.unit,
            discount_amount=item.discount_amount,
            discount_percent=item.discount_percent,
            gst_rate=item.gst_rate,
            gst_classification=GstClassification(item.gst_classification),
        )
        for item in data.items
    ]

    result = calculate_taxes(
        supplier_state_code=data.supplier_state_code,
        place_of_supply=data.place_of_supply,
        items=tax_inputs,
        apply_round_off=data.apply_round_off,
    )

    lines_out = [
        InvoiceItemOut(
            item_order=line.item_order,
            description=line.description,
            hsn_sac_code=line.hsn_sac_code,
            item_type=line.item_type,
            quantity=line.quantity,
            unit=line.unit,
            unit_price=line.unit_price,
            gross_amount=line.gross_amount,
            discount_percent=line.discount_percent,
            discount_amount=line.discount_amount,
            taxable_amount=line.taxable_amount,
            gst_classification=line.gst_classification,
            gst_rate=line.gst_rate,
            cgst_rate=line.cgst_rate,
            cgst_amount=line.cgst_amount,
            sgst_rate=line.sgst_rate,
            sgst_amount=line.sgst_amount,
            igst_rate=line.igst_rate,
            igst_amount=line.igst_amount,
            total_tax_amount=line.total_tax_amount,
            line_total=line.line_total,
        )
        for line in result.lines
    ]

    return TaxPreviewResponse(
        supplier_state_code=result.supplier_state_code,
        place_of_supply=result.place_of_supply,
        is_intra_state=result.is_intra_state,
        apply_round_off=result.apply_round_off,
        lines=lines_out,
        total_gross_amount=result.total_gross_amount,
        total_discount_amount=result.total_discount_amount,
        taxable_amount=result.taxable_amount,
        cgst_amount=result.cgst_amount,
        sgst_amount=result.sgst_amount,
        igst_amount=result.igst_amount,
        total_tax_amount=result.total_tax_amount,
        round_off=result.round_off,
        grand_total=result.grand_total,
    )


@router.post("", response_model=SalesInvoiceOut, status_code=status.HTTP_201_CREATED)
@router.post("/drafts", response_model=SalesInvoiceOut, status_code=status.HTTP_201_CREATED)
@requires(INVOICE_SALES_CREATE)
def create_draft(
    data: SalesInvoiceDraftCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new sales invoice draft."""
    invoice = create_sales_invoice_draft(db, ctx, data)
    return _build_sales_invoice_out(db, invoice)


@router.post("/signatures/temporary", response_model=TemporarySignatureUploadOut)
@requires(INVOICE_SALES_CREATE)
async def upload_temporary_signature(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not accessible to master admin")

    # 1. Size check (2MB)
    max_bytes = 2 * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signature file size ({len(content)} bytes) exceeds maximum limit of 2MB",
        )

    # 2. Rejection of SVG and scripts
    content_lower = content[:1024].lower()
    if b"<svg" in content_lower or b"<?xml" in content_lower:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SVG format is not allowed for signature images",
        )

    is_png = content.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = content.startswith(b"\xff\xd8\xff")
    if not (is_png or is_jpeg):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Only PNG, JPG, and JPEG files are supported.",
        )

    # 3. Decode with PIL and validate
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupted or invalid image file",
        )

    # EXIF auto-orientation
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Ensure RGBA to preserve PNG alpha channel
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Clean re-encode to PNG to strip polyglots / unwanted metadata
    out_buf = io.BytesIO()
    img.save(out_buf, format="PNG", optimize=True)
    clean_bytes = out_buf.getvalue()
    clean_sha256 = hashlib.sha256(clean_bytes).hexdigest()

    # Generate secure random upload token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # Save to company-scoped temporary storage path
    tmp_key = f"signatures/tmp/{ctx.company_id}/{token_hash}.png"
    storage_dir = Path(settings.STORAGE_PATH)
    full_path = storage_dir / tmp_key
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(clean_bytes)

    width_px, height_px = img.size
    aspect_ratio = Decimal(str(round(width_px / max(1, height_px), 4)))
    default_w = Decimal("45.00")
    default_h = Decimal(str(round(45.0 / float(aspect_ratio), 2)))

    # Persist temporary upload tracking record
    temp_record = TemporarySignatureUpload(
        upload_token_hash=token_hash,
        company_id=ctx.company_id,
        branch_id=ctx.branch_id,
        user_id=ctx.user_id,
        storage_key=tmp_key,
        original_filename=file.filename or "signature.png",
        mime_type="image/png",
        file_size=len(clean_bytes),
        sha256=clean_sha256,
        aspect_ratio=aspect_ratio,
        width_px=width_px,
        height_px=height_px,
        consumed=False,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    db.add(temp_record)
    db.commit()

    return TemporarySignatureUploadOut(
        upload_token=raw_token,
        temp_view_url=f"/api/sales-invoices/signatures/temp/{raw_token}",
        aspect_ratio=aspect_ratio,
        width_px=width_px,
        height_px=height_px,
        default_width_mm=default_w,
        default_height_mm=default_h,
    )


@router.get("/signatures/temp/{token}")
def get_temporary_signature_image(
    token: str,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context_from_query),
):
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not accessible to master admin")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    rec = (
        db.query(TemporarySignatureUpload)
        .filter(
            TemporarySignatureUpload.upload_token_hash == token_hash,
            TemporarySignatureUpload.company_id == ctx.company_id,
        )
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporary signature not found")

    now = datetime.now(timezone.utc) if rec.expires_at.tzinfo else datetime.utcnow()
    if rec.expires_at < now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporary signature expired")

    file_path = Path(settings.STORAGE_PATH) / rec.storage_key
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature image file not found")

    return FileResponse(
        path=str(file_path),
        media_type="image/png",
        filename=rec.original_filename,
    )


@router.get("/signatures/{sig_id}/image")
def get_signature_image(
    sig_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context_from_query),
):
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not accessible to master admin")

    sig = (
        db.query(SalesInvoiceSignature)
        .filter(
            SalesInvoiceSignature.id == sig_id,
            SalesInvoiceSignature.company_id == ctx.company_id,
        )
        .first()
    )
    if not sig:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature not found")

    file_path = Path(settings.STORAGE_PATH) / sig.storage_key
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature image file not found")

    return FileResponse(
        path=str(file_path),
        media_type="image/png",
        filename=sig.original_filename,
    )


@router.get("/drafts/{invoice_id}/preview-page")
@router.get("/{invoice_id}/preview-page")
def get_draft_preview_page(
    invoice_id: int,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context_from_query),
):
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not accessible to master admin")

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == ctx.company_id,
            Invoice.deleted_at.is_(None),
        )
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice draft not found")

    DocumentAccessPolicy.verify_invoice_access(ctx, INVOICE_SALES_VIEW, invoice)

    pdf_bytes = render_draft_sales_invoice_pdf_bytes(db=db, invoice=invoice)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    target_page = min(max(1, page), total_pages)

    pixmap = doc[target_page - 1].get_pixmap(dpi=150)
    png_bytes = pixmap.tobytes("png")
    doc.close()

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-Total-Pages": str(total_pages),
            "X-Current-Page": str(target_page),
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("/{invoice_id}", response_model=SalesInvoiceOut)
@requires(INVOICE_SALES_VIEW)
def get_sales_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve full details of a sales invoice."""
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.company_id == ctx.company_id)
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice not found")

    DocumentAccessPolicy.verify_invoice_access(ctx, INVOICE_SALES_VIEW, invoice)
    return _build_sales_invoice_out(db, invoice)


@router.put("/{invoice_id}", response_model=SalesInvoiceOut)
@router.put("/drafts/{invoice_id}", response_model=SalesInvoiceOut)
@router.put("/{invoice_id}/draft", response_model=SalesInvoiceOut)
@requires(INVOICE_SALES_EDIT)
def update_draft(
    invoice_id: int,
    data: SalesInvoiceDraftUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update fields and recalculate totals for an existing draft."""
    invoice = update_sales_invoice_draft(db, ctx, invoice_id, data)
    return _build_sales_invoice_out(db, invoice)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{invoice_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
@requires(INVOICE_SALES_DISCARD)
def discard_draft(
    invoice_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Soft-discard an unissued draft."""
    discard_sales_invoice_draft(db, ctx, invoice_id)
    return None


@router.get("/{invoice_id}/pdf")
@requires(INVOICE_SALES_VIEW)
def get_sales_invoice_pdf(
    invoice_id: int,
    download: bool = Query(False),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Serve or download the approved sales invoice PDF."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == ctx.company_id,
            Invoice.deleted_at.is_(None),
        )
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice not found")

    if invoice.status not in ("approved", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PDF is only available for approved or cancelled invoices. Current status: '{invoice.status}'",
        )

    if not invoice.pdf_filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF has not been generated for this invoice")

    storage_adapter = get_storage_adapter()
    try:
        pdf_bytes = storage_adapter.read(invoice.pdf_filename)
    except Exception:
        # Fallback to local storage path
        pdf_path = Path(settings.STORAGE_PATH) / invoice.pdf_filename
        if not pdf_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice PDF file missing from storage")
        pdf_bytes = pdf_path.read_bytes()

    disp = "attachment" if download else "inline"
    clean_name = f"invoice_{invoice.invoice_number.replace('/', '_')}.pdf" if invoice.invoice_number else f"sales_invoice_{invoice.id}.pdf"

    audit.record_event(
        db=db,
        action=events.DOCUMENT_DOWNLOAD if download else events.DOCUMENT_VIEW,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
        metadata={"invoice_number": invoice.invoice_number, "download": download},
    )
    db.commit()

    from fastapi.responses import Response
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{clean_name}"'},
    )


@router.post("/{invoice_id}/submit", response_model=SalesInvoiceOut)
@requires(INVOICE_SALES_SUBMIT)
def submit_draft(
    invoice_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Submit a draft for approval."""
    invoice = submit_sales_invoice_for_approval(db, ctx, invoice_id)
    return _build_sales_invoice_out(db, invoice)


@router.post("/{invoice_id}/approve", response_model=SalesInvoiceOut)
@requires(INVOICE_SALES_APPROVE)
def approve_and_issue(
    invoice_id: int,
    data: Optional[SalesInvoiceApprovalInput] = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """
    Approve and issue invoice: allocates invoice number, renders immutable PDF,
    and transitions to 'approved'. Enforces strict separation of duties.
    """
    approval_notes = data.notes if data else None
    invoice = approve_and_issue_sales_invoice(db, ctx, invoice_id, approval_notes=approval_notes)
    return _build_sales_invoice_out(db, invoice)


@router.post("/{invoice_id}/reject", response_model=SalesInvoiceOut)
@requires(INVOICE_SALES_APPROVE)
def reject_to_draft(
    invoice_id: int,
    data: Optional[SalesInvoiceApprovalInput] = None,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Reject a submitted invoice back to draft status."""
    rejection_notes = data.notes if data else None
    invoice = reject_sales_invoice(db, ctx, invoice_id, rejection_notes=rejection_notes)
    return _build_sales_invoice_out(db, invoice)


@router.post("/{invoice_id}/cancel", response_model=SalesInvoiceOut)
@requires(INVOICE_SALES_CANCEL)
def cancel_invoice(
    invoice_id: int,
    data: SalesInvoiceCancelInput,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Cancel an approved outbound sales invoice."""
    invoice = cancel_sales_invoice(db, ctx, invoice_id, reason=data.reason)
    return _build_sales_invoice_out(db, invoice)
