"""
Authoritative Outbound Sales Invoice Issuance Service (Module 13).

Manages the complete sales invoice lifecycle:
  1. Draft creation and editing with deterministic pure-Decimal tax calculations.
  2. Draft submission for approval.
  3. Strict Separation of Duties under 'admin_only' policy:
     - Creator cannot approve their own invoice (no exception for Global Admin).
     - Master Admin is hard-blocked (404/403).
  4. Two-phase Issuance:
     - Phase A: Transactional invoice number reservation (Rule 46(b) compliant).
     - Phase B: WeasyPrint PDF generation and SHA-256 computation.
     - Phase C: Finalization to 'approved'.
  5. Retry resilience: Failed PDF storage leaves invoice in 'pending_issuance',
     allowing retries without burning a new invoice sequence number.
  6. Cancellation with mandatory reason under supported policy.
  7. Full audit event recording.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import io
import os
from pathlib import Path
import shutil
import uuid
from typing import Optional, List, Dict, Any, Union
from fastapi import HTTPException, status
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
import weasyprint
import fitz

from app.audit import events
from app.audit.service import audit
from app.auth.permissions import (
    INVOICE_SALES_CREATE,
    INVOICE_SALES_EDIT,
    INVOICE_SALES_DISCARD,
    INVOICE_SALES_SUBMIT,
    INVOICE_SALES_APPROVE,
    INVOICE_SALES_CANCEL,
    INVOICE_SALES_VIEW,
)
from app.config import settings
from app.context import AuthContext, MasterAdminContext
from app.models import (
    Company,
    Branch,
    Customer,
    CustomerAddress,
    GstRegistration,
    Invoice,
    OutboundSalesInvoice,
    InvoiceItem,
    SalesInvoiceSignature,
    TemporarySignatureUpload,
    UserRole,
)
from app.schemas import (
    SalesInvoiceDraftCreate,
    SalesInvoiceDraftUpdate,
    InvoiceItemInput,
    SignatureLayoutInput,
)
from app.services.gstin_validator import INDIAN_GST_STATE_CODES
from app.services.invoice_numbering import reserve_invoice_number, get_current_financial_year
from app.services.tax_engine import (
    calculate_taxes,
    TaxLineInput,
    GstClassification,
)


def _get_jinja_env() -> Environment:
    templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env


def _render_and_save_sales_invoice_pdf(
    invoice: Invoice,
    sales_detail: OutboundSalesInvoice,
    gst_reg: GstRegistration,
    customer: Customer,
    items: List[InvoiceItem],
    billing_addr: Optional[CustomerAddress] = None,
    shipping_addr: Optional[CustomerAddress] = None,
) -> tuple[str, str, int]:
    """
    Renders sales_invoice.html via WeasyPrint and saves it to storage.
    Returns (filename, sha256_hash, file_size_bytes).
    """
    env = _get_jinja_env()
    template = env.get_template("sales_invoice.html")

    is_intra = (str(gst_reg.state_code).strip().zfill(2) == str(sales_detail.place_of_supply).strip().zfill(2))
    pos_name = INDIAN_GST_STATE_CODES.get(str(sales_detail.place_of_supply).strip().zfill(2), sales_detail.place_of_supply)

    inv_view = {
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.strftime("%d-%b-%Y") if invoice.invoice_date else "",
        "due_date": invoice.due_date.strftime("%d-%b-%Y") if invoice.due_date else "",
        "financial_year": invoice.financial_year or "",
        "place_of_supply": sales_detail.place_of_supply,
        "place_of_supply_name": pos_name,
        "is_intra_state": is_intra,
        "taxable_amount": invoice.taxable_amount or Decimal("0.00"),
        "cgst_amount": invoice.cgst_amount or Decimal("0.00"),
        "sgst_amount": invoice.sgst_amount or Decimal("0.00"),
        "igst_amount": invoice.igst_amount or Decimal("0.00"),
        "round_off": invoice.round_off or Decimal("0.00"),
        "grand_total": invoice.grand_total or Decimal("0.00"),
        "notes": invoice.notes or "",
        "terms_and_conditions": getattr(sales_detail, "terms_and_conditions", None) or "",
    }

    supplier_view = {
        "legal_name": gst_reg.legal_name,
        "trade_name": gst_reg.trade_name,
        "gstin": gst_reg.gstin,
        "state_code": gst_reg.state_code,
        "state_name": gst_reg.state_name,
        "registered_address": gst_reg.registered_address or "",
    }

    customer_view = {
        "name": customer.name,
        "gstin": customer.gstin,
        "is_b2c": customer.is_b2c,
    }

    rendered_html = template.render(
        invoice=inv_view,
        supplier=supplier_view,
        customer=customer_view,
        items=items,
        billing_address=billing_addr,
        shipping_address=shipping_addr,
    )

    pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()

    # Precision signature stamping via PyMuPDF
    signatures = getattr(invoice, "signatures", [])
    if signatures:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        mm_to_pts = 72.0 / 25.4

        for sig in signatures:
            target_page_num = total_pages if sig.is_pinned_to_last_page else sig.page_number
            if target_page_num < 1 or target_page_num > total_pages:
                target_page_num = min(max(1, target_page_num), total_pages)

            page = doc[target_page_num - 1]
            x0 = float(sig.x_mm) * mm_to_pts
            y0 = float(sig.y_mm) * mm_to_pts
            x1 = (float(sig.x_mm) + float(sig.width_mm)) * mm_to_pts
            y1 = (float(sig.y_mm) + float(sig.height_mm)) * mm_to_pts
            rect = fitz.Rect(x0, y0, x1, y1)

            sig_path = Path(settings.STORAGE_PATH) / sig.storage_key
            if sig_path.exists():
                sig_bytes = sig_path.read_bytes()
                page.insert_image(rect, stream=sig_bytes, keep_proportion=True)

        pdf_bytes = doc.tobytes(garbage=3, deflate=True)
        doc.close()

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    file_size = len(pdf_bytes)

    fy_safe = (invoice.financial_year or "FY").replace("-", "_")
    inv_num_safe = (invoice.invoice_number or f"INV_{invoice.id}").replace("/", "_")
    filename = f"sales_invoice_{invoice.id}_{fy_safe}_{inv_num_safe}.pdf"

    storage_dir = Path(settings.STORAGE_PATH)
    storage_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = storage_dir / filename
    pdf_path.write_bytes(pdf_bytes)

    # Sync to repo storage root as well if separate
    try:
        repo_storage = Path("./storage/documents")
        if repo_storage.resolve() != storage_dir.resolve():
            repo_storage.mkdir(parents=True, exist_ok=True)
            (repo_storage / filename).write_bytes(pdf_bytes)
    except Exception:
        pass

    return filename, pdf_sha256, file_size


def _sync_invoice_signatures(
    db: Session,
    invoice: Invoice,
    signatures_data: Optional[List[SignatureLayoutInput]],
    company_id: int,
):
    """
    Synchronizes signature records with an invoice draft.
    Validates physical A4 boundaries and handles temporary upload consumption.
    """
    if signatures_data is None:
        return

    # Check invoice status - immutability guard
    if invoice.status in ("approved", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify signatures on an {invoice.status} invoice",
        )

    # Validate coordinate constraints on each item
    for item in signatures_data:
        if item.page_number < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Signature page_number must be >= 1",
            )
        if item.x_mm < Decimal("0.0") or item.y_mm < Decimal("0.0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Signature coordinates (x_mm, y_mm) must be >= 0",
            )
        if item.width_mm < Decimal("10.0") or item.height_mm < Decimal("5.0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Signature dimensions must be at least 10mm width and 5mm height",
            )
        if (item.x_mm + item.width_mm) > Decimal("210.0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Signature exceeds page width: x_mm ({item.x_mm}) + width_mm ({item.width_mm}) > 210mm",
            )
        if (item.y_mm + item.height_mm) > Decimal("297.0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Signature exceeds page height: y_mm ({item.y_mm}) + height_mm ({item.height_mm}) > 297mm",
            )

    # Get existing signatures for this invoice
    existing_sigs = {
        s.id: s
        for s in db.query(SalesInvoiceSignature)
        .filter(
            SalesInvoiceSignature.invoice_id == invoice.id,
            SalesInvoiceSignature.company_id == company_id,
        )
        .all()
    }

    retained_sig_ids = set()

    for item in signatures_data:
        if item.id and item.id in existing_sigs:
            # Update existing signature layout
            sig = existing_sigs[item.id]
            sig.page_number = item.page_number
            sig.is_pinned_to_last_page = item.is_pinned_to_last_page
            sig.x_mm = item.x_mm
            sig.y_mm = item.y_mm
            sig.width_mm = item.width_mm
            sig.height_mm = item.height_mm
            sig.updated_at = datetime.utcnow()
            retained_sig_ids.add(sig.id)
        elif item.upload_token:
            # Associate new temporary signature upload
            token_hash = hashlib.sha256(item.upload_token.encode("utf-8")).hexdigest()
            temp_upload = (
                db.query(TemporarySignatureUpload)
                .filter(
                    TemporarySignatureUpload.upload_token_hash == token_hash,
                    TemporarySignatureUpload.company_id == company_id,
                    TemporarySignatureUpload.consumed == False,
                )
                .with_for_update()
                .first()
            )
            if not temp_upload:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Signature upload token not found or already consumed",
                )
            now = datetime.now(timezone.utc) if temp_upload.expires_at.tzinfo else datetime.utcnow()
            if temp_upload.expires_at < now:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Signature upload token has expired",
                )

            # Move/copy file to permanent storage key
            perm_key = f"signatures/{company_id}/{invoice.id}_{uuid.uuid4().hex}.png"
            storage_dir = Path(settings.STORAGE_PATH)
            src_file = storage_dir / temp_upload.storage_key
            dest_file = storage_dir / perm_key
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            if src_file.exists():
                shutil.copy2(src_file, dest_file)
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Temporary signature image file missing from storage",
                )

            temp_upload.consumed = True

            new_sig = SalesInvoiceSignature(
                company_id=company_id,
                invoice_id=invoice.id,
                storage_key=perm_key,
                original_filename=temp_upload.original_filename,
                mime_type=temp_upload.mime_type,
                file_size=temp_upload.file_size,
                sha256=temp_upload.sha256,
                page_number=item.page_number,
                is_pinned_to_last_page=item.is_pinned_to_last_page,
                x_mm=item.x_mm,
                y_mm=item.y_mm,
                width_mm=item.width_mm,
                height_mm=item.height_mm,
            )
            db.add(new_sig)
            db.flush()
            retained_sig_ids.add(new_sig.id)

    # Delete un-retained existing signatures
    for s_id, s_obj in existing_sigs.items():
        if s_id not in retained_sig_ids:
            try:
                sig_file = Path(settings.STORAGE_PATH) / s_obj.storage_key
                if sig_file.exists():
                    sig_file.unlink()
            except Exception:
                pass
            db.delete(s_obj)


def render_draft_sales_invoice_pdf_bytes(
    db: Session,
    invoice: Invoice,
) -> bytes:
    """Renders draft sales invoice to PDF bytes via WeasyPrint."""
    sales_detail = invoice.sales_detail
    gst_reg = sales_detail.gst_registration if sales_detail else None
    if not gst_reg and invoice.gst_registration_id:
        gst_reg = db.query(GstRegistration).filter(
            GstRegistration.id == invoice.gst_registration_id,
            GstRegistration.company_id == invoice.company_id,
        ).first()

    customer = sales_detail.customer if sales_detail else None
    if not customer and sales_detail:
        customer = db.query(Customer).filter(
            Customer.id == sales_detail.customer_id,
            Customer.company_id == invoice.company_id,
        ).first()

    billing_addr = sales_detail.billing_address if sales_detail else None
    shipping_addr = sales_detail.shipping_address if sales_detail else None
    items = sorted(invoice.items, key=lambda x: x.line_number)

    env = _get_jinja_env()
    template = env.get_template("sales_invoice.html")

    pos = sales_detail.place_of_supply if (sales_detail and hasattr(sales_detail, "place_of_supply")) else "33"
    state_code = gst_reg.state_code if gst_reg else "33"
    is_intra = (str(state_code).strip().zfill(2) == str(pos).strip().zfill(2))
    pos_name = INDIAN_GST_STATE_CODES.get(str(pos).strip().zfill(2), pos)

    inv_view = {
        "invoice_number": invoice.invoice_number or "DRAFT PREVIEW",
        "invoice_date": invoice.invoice_date.strftime("%d-%b-%Y") if invoice.invoice_date else date.today().strftime("%d-%b-%Y"),
        "due_date": invoice.due_date.strftime("%d-%b-%Y") if invoice.due_date else "",
        "financial_year": invoice.financial_year or "",
        "place_of_supply": pos,
        "place_of_supply_name": pos_name,
        "is_intra_state": is_intra,
        "taxable_amount": invoice.taxable_amount or Decimal("0.00"),
        "cgst_amount": invoice.cgst_amount or Decimal("0.00"),
        "sgst_amount": invoice.sgst_amount or Decimal("0.00"),
        "igst_amount": invoice.igst_amount or Decimal("0.00"),
        "round_off": invoice.round_off or Decimal("0.00"),
        "grand_total": invoice.grand_total or Decimal("0.00"),
        "notes": invoice.notes or "",
        "terms_and_conditions": getattr(sales_detail, "terms_and_conditions", None) or "",
    }

    supplier_view = {
        "legal_name": gst_reg.legal_name if gst_reg else invoice.seller_name or "",
        "trade_name": gst_reg.trade_name if gst_reg else "",
        "gstin": gst_reg.gstin if gst_reg else invoice.seller_gstin or "",
        "state_code": gst_reg.state_code if gst_reg else "33",
        "state_name": gst_reg.state_name if gst_reg else "Tamil Nadu",
        "registered_address": (gst_reg.registered_address if gst_reg else "") or "",
    }

    customer_view = {
        "name": customer.name if customer else invoice.buyer_name or "",
        "gstin": customer.gstin if customer else invoice.buyer_gstin or "",
        "is_b2c": customer.is_b2c if customer else False,
    }

    rendered_html = template.render(
        invoice=inv_view,
        supplier=supplier_view,
        customer=customer_view,
        items=items,
        billing_address=billing_addr,
        shipping_address=shipping_addr,
    )

    pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
    return pdf_bytes


def cleanup_expired_signature_uploads(db: Session) -> int:
    """Removes unconsumed temporary signature uploads older than their expiration time."""
    now = datetime.now(timezone.utc)
    expired = (
        db.query(TemporarySignatureUpload)
        .filter(
            TemporarySignatureUpload.expires_at < now,
            TemporarySignatureUpload.consumed == False,
        )
        .all()
    )
    count = 0
    storage_dir = Path(settings.STORAGE_PATH)
    for rec in expired:
        try:
            f = storage_dir / rec.storage_key
            if f.exists():
                f.unlink()
        except Exception:
            pass
        db.delete(rec)
        count += 1
    if count > 0:
        db.commit()
    return count


def create_sales_invoice_draft(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    draft_data: SalesInvoiceDraftCreate,
) -> Invoice:
    """Creates a new outbound sales invoice draft."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    if INVOICE_SALES_CREATE not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: You do not have permission to create sales invoices",
        )

    # Branch scoping check
    if not (ctx.is_global_admin or draft_data.branch_id in ctx.assigned_branch_ids or draft_data.branch_id == ctx.branch_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to create invoices in this branch",
        )

    # Verify customer
    customer = (
        db.query(Customer)
        .filter(Customer.company_id == ctx.company_id, Customer.id == draft_data.customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # Verify GST registration
    gst_reg = (
        db.query(GstRegistration)
        .filter(
            GstRegistration.company_id == ctx.company_id,
            GstRegistration.id == draft_data.gst_registration_id,
            GstRegistration.is_active == True,
        )
        .first()
    )
    if not gst_reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active GST registration not found")

    # Verify addresses if provided
    if draft_data.billing_address_id:
        b_addr = (
            db.query(CustomerAddress)
            .filter(
                CustomerAddress.customer_id == customer.id,
                CustomerAddress.id == draft_data.billing_address_id,
            )
            .first()
        )
        if not b_addr:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid billing address for customer")

    if draft_data.shipping_address_id:
        s_addr = (
            db.query(CustomerAddress)
            .filter(
                CustomerAddress.customer_id == customer.id,
                CustomerAddress.id == draft_data.shipping_address_id,
            )
            .first()
        )
        if not s_addr:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid shipping address for customer")

    # Deterministic tax calculation
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
        for item in draft_data.items
    ]

    tax_result = calculate_taxes(
        supplier_state_code=gst_reg.state_code,
        place_of_supply=draft_data.place_of_supply,
        items=tax_inputs,
        apply_round_off=draft_data.apply_round_off,
    )

    inv_date = draft_data.invoice_date or date.today()
    fy = get_current_financial_year(inv_date)

    # Header record
    invoice = Invoice(
        company_id=ctx.company_id,
        branch_id=draft_data.branch_id,
        gst_registration_id=gst_reg.id,
        kind="generated",
        status="draft",
        invoice_number=None,  # Must be null while draft
        invoice_date=inv_date,
        due_date=draft_data.due_date,
        taxable_amount=tax_result.taxable_amount,
        cgst_amount=tax_result.cgst_amount,
        sgst_amount=tax_result.sgst_amount,
        igst_amount=tax_result.igst_amount,
        round_off=tax_result.round_off,
        grand_total=tax_result.grand_total,
        currency="INR",
        notes=draft_data.notes,
        created_by=ctx.user_id,
        seller_name=gst_reg.legal_name,
        seller_gstin=gst_reg.gstin,
        buyer_name=customer.name,
        buyer_gstin=customer.gstin,
    )
    db.add(invoice)
    db.flush()

    # Outbound details
    sales_detail = OutboundSalesInvoice(
        company_id=ctx.company_id,
        invoice_id=invoice.id,
        customer_id=customer.id,
        gst_registration_id=gst_reg.id,
        billing_address_id=draft_data.billing_address_id,
        shipping_address_id=draft_data.shipping_address_id,
        place_of_supply_state_code=tax_result.place_of_supply,
        place_of_supply_state_name=INDIAN_GST_STATE_CODES.get(tax_result.place_of_supply, tax_result.place_of_supply),
        financial_year=fy,
        series_code=(draft_data.series_code or "INV").strip().upper(),
        is_b2c=customer.is_b2c,
    )
    db.add(sales_detail)

    # Line items
    for line in tax_result.lines:
        db_item = InvoiceItem(
            invoice_id=invoice.id,
            line_number=line.item_order,
            item_description=line.description,
            hsn_sac=line.hsn_sac_code,
            item_type=line.item_type,
            quantity=line.quantity,
            unit_of_measure=line.unit,
            unit_price=line.unit_price,
            discount_percent=line.discount_percent,
            discount_amount=line.discount_amount,
            taxable_value=line.taxable_amount,
            gst_rate=line.gst_rate,
            cgst_rate=line.cgst_rate,
            cgst_amount=line.cgst_amount,
            sgst_rate=line.sgst_rate,
            sgst_amount=line.sgst_amount,
            igst_rate=line.igst_rate,
            igst_amount=line.igst_amount,
            line_total=line.line_total,
            is_zero_rated=(line.gst_classification != "TAXABLE"),
        )
        db.add(db_item)

    if draft_data.signatures:
        _sync_invoice_signatures(
            db=db,
            invoice=invoice,
            signatures_data=draft_data.signatures,
            company_id=ctx.company_id,
        )

    db.commit()
    db.refresh(invoice)

    audit.record_event(
        db=db,
        action=events.SALES_INVOICE_DRAFT_CREATED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
        metadata={"grand_total": str(invoice.grand_total), "customer_id": customer.id},
    )

    return invoice


def update_sales_invoice_draft(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    invoice_id: int,
    update_data: SalesInvoiceDraftUpdate,
) -> Invoice:
    """Updates an existing sales invoice draft."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if INVOICE_SALES_EDIT not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: You do not have permission to edit sales invoices",
        )

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == ctx.company_id,
            Invoice.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice not found")

    if invoice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit invoice in status '{invoice.status}'. Only drafts can be modified.",
        )

    # Staff draft ownership check
    if ctx.role == UserRole.STAFF and invoice.created_by != ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff users can only edit their own drafts",
        )

    sales_detail = invoice.sales_detail
    if not sales_detail:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sales invoice details missing")

    if update_data.branch_id is not None:
        if not (ctx.is_global_admin or update_data.branch_id in ctx.assigned_branch_ids or update_data.branch_id == ctx.branch_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to target branch")
        invoice.branch_id = update_data.branch_id

    if update_data.customer_id is not None:
        cust = db.query(Customer).filter(Customer.company_id == ctx.company_id, Customer.id == update_data.customer_id).first()
        if not cust:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
        sales_detail.customer_id = cust.id
        invoice.buyer_name = cust.name
        invoice.buyer_gstin = cust.gstin

    if update_data.gst_registration_id is not None:
        gst_reg = db.query(GstRegistration).filter(
            GstRegistration.company_id == ctx.company_id,
            GstRegistration.id == update_data.gst_registration_id,
            GstRegistration.is_active == True,
        ).first()
        if not gst_reg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active GST registration not found")
        invoice.gst_registration_id = gst_reg.id
        sales_detail.gst_registration_id = gst_reg.id
        invoice.seller_name = gst_reg.legal_name
        invoice.seller_gstin = gst_reg.gstin

    if update_data.billing_address_id is not None:
        sales_detail.billing_address_id = update_data.billing_address_id

    if update_data.shipping_address_id is not None:
        sales_detail.shipping_address_id = update_data.shipping_address_id

    if update_data.place_of_supply is not None:
        pos_code = update_data.place_of_supply.strip().zfill(2)
        sales_detail.place_of_supply_state_code = pos_code
        sales_detail.place_of_supply_state_name = INDIAN_GST_STATE_CODES.get(pos_code, pos_code)

    if update_data.invoice_date is not None:
        invoice.invoice_date = update_data.invoice_date
        fy = get_current_financial_year(update_data.invoice_date)
        sales_detail.financial_year = fy

    if update_data.due_date is not None:
        invoice.due_date = update_data.due_date

    if update_data.notes is not None:
        invoice.notes = update_data.notes

    # Recalculate line items if provided
    if update_data.items is not None:
        # Delete old items
        db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).delete()

        current_gst_reg = sales_detail.gst_registration
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
            for item in update_data.items
        ]

        tax_result = calculate_taxes(
            supplier_state_code=current_gst_reg.state_code,
            place_of_supply=sales_detail.place_of_supply_state_code,
            items=tax_inputs,
            apply_round_off=bool(update_data.apply_round_off),
        )

        invoice.taxable_amount = tax_result.taxable_amount
        invoice.cgst_amount = tax_result.cgst_amount
        invoice.sgst_amount = tax_result.sgst_amount
        invoice.igst_amount = tax_result.igst_amount
        invoice.round_off = tax_result.round_off
        invoice.grand_total = tax_result.grand_total

        for line in tax_result.lines:
            db_item = InvoiceItem(
                invoice_id=invoice.id,
                line_number=line.item_order,
                item_description=line.description,
                hsn_sac=line.hsn_sac_code,
                item_type=line.item_type,
                quantity=line.quantity,
                unit_of_measure=line.unit,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                discount_amount=line.discount_amount,
                taxable_value=line.taxable_amount,
                gst_rate=line.gst_rate,
                cgst_rate=line.cgst_rate,
                cgst_amount=line.cgst_amount,
                sgst_rate=line.sgst_rate,
                sgst_amount=line.sgst_amount,
                igst_rate=line.igst_rate,
                igst_amount=line.igst_amount,
                line_total=line.line_total,
                is_zero_rated=(line.gst_classification != "TAXABLE"),
            )
            db.add(db_item)

    if update_data.signatures is not None:
        _sync_invoice_signatures(
            db=db,
            invoice=invoice,
            signatures_data=update_data.signatures,
            company_id=ctx.company_id,
        )

    invoice.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)

    audit.record_event(
        db=db,
        action=events.SALES_INVOICE_DRAFT_UPDATED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
        metadata={"grand_total": str(invoice.grand_total)},
    )

    return invoice


def discard_sales_invoice_draft(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    invoice_id: int,
) -> None:
    """Soft-discards an unissued sales invoice draft."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if INVOICE_SALES_DISCARD not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: You do not have permission to discard sales invoices",
        )

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

    if invoice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot discard invoice in status '{invoice.status}'. Only drafts can be discarded.",
        )

    if ctx.role == UserRole.STAFF and invoice.created_by != ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff users can only discard their own drafts",
        )

    invoice.deleted_at = datetime.now(timezone.utc)
    invoice.updated_at = datetime.now(timezone.utc)
    db.commit()

    audit.record_event(
        db=db,
        action=events.SALES_INVOICE_DRAFT_DISCARDED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
    )


def submit_sales_invoice_for_approval(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    invoice_id: int,
) -> Invoice:
    """Submits a sales invoice draft for management approval."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if INVOICE_SALES_SUBMIT not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: You do not have permission to submit sales invoices",
        )

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == ctx.company_id,
            Invoice.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice not found")

    if invoice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice cannot be submitted from status '{invoice.status}'. Expected 'draft'.",
        )

    # Check at least one item
    item_count = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).count()
    if item_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invoice must have at least one line item before submission.",
        )

    if invoice.grand_total is None or invoice.grand_total < Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invoice must have a valid grand total before submission.",
        )

    invoice.status = "pending_approval"
    invoice.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)

    audit.record_event(
        db=db,
        action=events.SALES_INVOICE_SUBMITTED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
    )

    return invoice


def reject_sales_invoice(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    invoice_id: int,
    rejection_notes: Optional[str] = None,
) -> Invoice:
    """Rejects a submitted invoice back to draft status."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if INVOICE_SALES_APPROVE not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: You do not have permission to approve or reject sales invoices",
        )

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == ctx.company_id,
            Invoice.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice not found")

    if invoice.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice in status '{invoice.status}' cannot be rejected. Expected 'pending_approval'.",
        )

    invoice.status = "draft"
    if rejection_notes:
        old_notes = invoice.notes or ""
        invoice.notes = f"{old_notes}\n[Rejection Reason]: {rejection_notes}".strip()
    invoice.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)

    audit.record_event(
        db=db,
        action=events.SALES_INVOICE_REJECTED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
        metadata={"rejection_notes": rejection_notes},
    )

    return invoice


def approve_and_issue_sales_invoice(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    invoice_id: int,
    approval_notes: Optional[str] = None,
) -> Invoice:
    """
    Approves and issues an outbound sales invoice:
      - Validates approval permissions and company separation of duties policy.
      - Strictly forbids self-approval under default 'admin_only' policy.
      - Reserves consecutive sequence number (GST Rule 46(b)).
      - Transitions to 'pending_issuance'.
      - Renders immutable PDF and stores SHA-256 hash.
      - Finalizes to 'approved'.
    """
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    if INVOICE_SALES_APPROVE not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: You do not have permission to approve sales invoices",
        )

    # 1. Fetch invoice and company inside transaction
    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == ctx.company_id,
            Invoice.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice not found")

    if invoice.status not in ("pending_approval", "pending_issuance"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice cannot be approved from status '{invoice.status}'. Expected 'pending_approval'.",
        )

    # 2. Separation of Duties Check
    company = db.query(Company).filter(Company.id == ctx.company_id).first()
    policy = company.invoice_approval_policy if company else "admin_only"

    # Default policy is 'admin_only': Creator CANNOT approve their own invoice (no exception for Global Admin)
    if invoice.created_by == ctx.user_id and policy != "allow_self_approval":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Separation of duties violation: An invoice cannot be approved by its creator.",
        )

    sales_detail = invoice.sales_detail
    if not sales_detail:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sales invoice details missing")

    gst_reg = sales_detail.gst_registration
    customer = sales_detail.customer
    items = sorted(invoice.items, key=lambda x: x.item_order)

    # 3. Number Reservation (Two-phase Issuance: Phase A)
    if not invoice.invoice_number:
        inv_number, fy = reserve_invoice_number(
            db=db,
            company_id=invoice.company_id,
            gst_registration_id=sales_detail.gst_registration_id,
            series_code=sales_detail.series_code or "INV",
            invoice_date=invoice.invoice_date or date.today(),
            financial_year=invoice.financial_year,
        )
        invoice.invoice_number = inv_number
        sales_detail.financial_year = fy
        invoice.status = "pending_issuance"
        db.flush()

    # 4. PDF Generation (Two-phase Issuance: Phase B)
    billing_addr = sales_detail.billing_address
    shipping_addr = sales_detail.shipping_address

    try:
        pdf_filename, pdf_sha256, file_size = _render_and_save_sales_invoice_pdf(
            invoice=invoice,
            sales_detail=sales_detail,
            gst_reg=gst_reg,
            customer=customer,
            items=items,
            billing_addr=billing_addr,
            shipping_addr=shipping_addr,
        )
    except Exception as e:
        # DB commit preserves the reserved number in pending_issuance for retry
        sales_detail.issuance_attempt_count = (sales_detail.issuance_attempt_count or 0) + 1
        sales_detail.issuance_error_details = str(e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed during issuance: {str(e)}. The invoice number '{invoice.invoice_number}' is reserved and issuance can be retried.",
        )

    # 5. Store PDF metadata during pending_issuance before approval
    now_utc = datetime.now(timezone.utc)
    invoice.pdf_filename = pdf_filename
    invoice.file_size = file_size
    sales_detail.pdf_storage_key = pdf_filename
    sales_detail.pdf_sha256 = pdf_sha256
    sales_detail.pdf_generated_at = now_utc
    sales_detail.approved_by = ctx.user_id
    sales_detail.approved_at = now_utc
    db.flush()

    # 6. Finalize status to approved (Two-phase Issuance: Phase C)
    invoice.status = "approved"
    invoice.updated_at = now_utc
    sales_detail.updated_at = now_utc

    db.commit()
    db.refresh(invoice)

    audit.record_event(
        db=db,
        action=events.SALES_INVOICE_APPROVED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
        metadata={
            "invoice_number": invoice.invoice_number,
            "grand_total": str(invoice.grand_total),
            "pdf_sha256": pdf_sha256,
        },
    )

    return invoice


def cancel_sales_invoice(
    db: Session,
    ctx: Union[AuthContext, MasterAdminContext],
    invoice_id: int,
    reason: str,
) -> Invoice:
    """Cancels an approved outbound sales invoice."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if INVOICE_SALES_CANCEL not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: You do not have permission to cancel sales invoices",
        )

    if not reason or not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cancellation reason is mandatory",
        )

    invoice = (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == ctx.company_id,
            Invoice.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not invoice or invoice.kind != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales invoice not found")

    if invoice.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only approved invoices can be cancelled. Current status is '{invoice.status}'.",
        )

    # Branch scoping check
    if not (ctx.is_global_admin or invoice.branch_id in ctx.assigned_branch_ids or invoice.branch_id == ctx.branch_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to invoice branch")

    now_utc = datetime.now(timezone.utc)
    invoice.status = "cancelled"
    old_notes = invoice.notes or ""
    invoice.notes = f"{old_notes}\n[Cancelled on {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} by user {ctx.user_id}]: {reason.strip()}".strip()
    invoice.updated_at = now_utc

    sales_detail = invoice.sales_detail
    if sales_detail:
        sales_detail.cancelled_at = now_utc
        sales_detail.cancelled_by = ctx.user_id
        sales_detail.cancellation_reason = reason.strip()
        sales_detail.updated_at = now_utc

    db.commit()
    db.refresh(invoice)

    audit.record_event(
        db=db,
        action=events.SALES_INVOICE_CANCELLED,
        auth_context=ctx,
        object_type=events.ObjectType.INVOICE.value,
        object_id=invoice.id,
        metadata={"invoice_number": invoice.invoice_number, "reason": reason},
    )

    return invoice
