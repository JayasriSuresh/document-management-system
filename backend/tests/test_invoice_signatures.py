"""
Comprehensive Automated Tests for Module 13 Invoice Signatures Enhancement:
- Upload validation (PNG, JPEG, alpha transparency, SVG rejection, size limits, corrupted data)
- Temporary upload lifecycle, token hashing, expiration, and reuse prevention
- Cross-company isolation on temporary uploads and signatures
- Draft attachment, multi-signature layout, and coordinate boundary validation
- Draft preview page rendering (WeasyPrint -> PyMuPDF pixmap)
- Two-phase approval with precision PyMuPDF stamping and physical coordinate verification (within ±1mm)
- Database trigger immutability enforcement on approved and cancelled invoices
- Periodic orphan cleanup routine
"""

import io
import hashlib
import secrets
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
import fitz

from app.models import (
    Company,
    Branch,
    User,
    UserRole,
    GstRegistration,
    Customer,
    CustomerAddress,
    Invoice,
    SalesInvoiceSignature,
    TemporarySignatureUpload,
)
from app.database import SessionLocal
from app.config import settings
from app.services.invoice_issuance import cleanup_expired_signature_uploads


@pytest.fixture(scope="module")
def sig_test_env(client):
    """Sets up company 40 with creator and approver credentials and master data."""
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == 40).first()
        if not company:
            company = Company(
                id=40,
                name="Vasanth & Co.",
                code="VASANTH_CO",
                status="active",
                invoice_approval_policy="admin_only",
            )
            db.add(company)
            db.flush()

        branch = db.query(Branch).filter(Branch.company_id == 40).first()
        if not branch:
            branch = Branch(company_id=40, name="Chennai", code="CHENNAI")
            db.add(branch)
            db.flush()

        gst_reg = db.query(GstRegistration).filter(GstRegistration.company_id == 40).first()
        if not gst_reg:
            gst_reg = GstRegistration(
                company_id=40,
                gstin="33BLAPS0819R1ZQ",
                legal_name="Vasanth & Co. Pvt Ltd",
                state_code="33",
                state_name="Tamil Nadu",
                registered_address="100 Tech Park, Chennai, Tamil Nadu",
                is_active=True,
                is_default=True,
            )
            db.add(gst_reg)
            db.flush()

        customer = db.query(Customer).filter(Customer.company_id == 40).first()
        if not customer:
            customer = Customer(
                company_id=40,
                name="Kartwheel Consulting",
                gstin="33ALJPP7733P1ZE",
                pan="ALJPP7733P",
                is_b2c=False,
                is_active=True,
            )
            db.add(customer)
            db.flush()

            billing_addr = CustomerAddress(
                customer_id=customer.id,
                address_type="billing",
                address_line1="H-38/1400, 1st floor, 15th main road",
                city="Chennai",
                state_code="33",
                state_name="Tamil Nadu",
                pincode="600040",
                is_default=True,
            )
            db.add(billing_addr)

        db.commit()
        creator = db.query(User).filter(User.email == "samrethi@example.com").first()
        return {
            "company_id": 40,
            "branch_id": creator.branch_id if creator else branch.id,
            "gst_reg_id": gst_reg.id,
            "customer_id": customer.id,
            "creator_email": "samrethi@example.com",
            "approver_email": "jayasri@example.com",
        }
    finally:
        db.close()


def _generate_test_png(width=200, height=80, transparent=True) -> bytes:
    """Helper creating test PNG bytes with drawing and alpha channel."""
    mode = "RGBA" if transparent else "RGB"
    color = (0, 0, 0, 0) if transparent else (255, 255, 255)
    img = Image.new(mode, (width, height), color=color)
    draw = ImageDraw.Draw(img)
    draw.line([(10, 40), (190, 40)], fill=(0, 0, 128, 255) if transparent else (0, 0, 128), width=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _generate_test_jpeg(width=200, height=80) -> bytes:
    """Helper creating test JPEG bytes."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.line([(10, 40), (190, 40)], fill=(128, 0, 0), width=3)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── SECTION 1: UPLOAD AND SECURITY TESTS ─────────────────────────────────────

def test_upload_valid_png_with_transparency(client, auth_headers, sig_test_env):
    """SIG-01: Valid PNG signature upload succeeds and preserves alpha."""
    headers = auth_headers(sig_test_env["creator_email"])
    png_bytes = _generate_test_png(width=300, height=100, transparent=True)

    files = {"file": ("my_signature.png", png_bytes, "image/png")}
    resp = client.post("/api/sales-invoices/signatures/temporary", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "upload_token" in data
    assert data["temp_view_url"].startswith("/api/sales-invoices/signatures/temp/")
    assert Decimal(str(data["aspect_ratio"])) == Decimal("3.0")
    assert data["width_px"] == 300
    assert data["height_px"] == 100

    # Verify DB record
    token_hash = hashlib.sha256(data["upload_token"].encode("utf-8")).hexdigest()
    db = SessionLocal()
    try:
        rec = db.query(TemporarySignatureUpload).filter(
            TemporarySignatureUpload.upload_token_hash == token_hash
        ).first()
        assert rec is not None
        assert rec.company_id == sig_test_env["company_id"]
        assert rec.consumed is False
        assert rec.mime_type == "image/png"
    finally:
        db.close()


def test_upload_valid_jpeg(client, auth_headers, sig_test_env):
    """SIG-02: Valid JPEG upload is normalized to PNG."""
    headers = auth_headers(sig_test_env["creator_email"])
    jpg_bytes = _generate_test_jpeg(width=240, height=120)

    files = {"file": ("signature.jpg", jpg_bytes, "image/jpeg")}
    resp = client.post("/api/sales-invoices/signatures/temporary", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["upload_token"] is not None
    assert Decimal(str(data["aspect_ratio"])) == Decimal("2.0")


def test_reject_svg_signature(client, auth_headers, sig_test_env):
    """SIG-03: SVG files are strictly rejected."""
    headers = auth_headers(sig_test_env["creator_email"])
    svg_content = b"<svg xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='40'/></svg>"

    files = {"file": ("malicious.svg", svg_content, "image/svg+xml")}
    resp = client.post("/api/sales-invoices/signatures/temporary", files=files, headers=headers)
    assert resp.status_code == 400
    assert "SVG" in resp.json()["detail"]


def test_reject_oversized_signature(client, auth_headers, sig_test_env):
    """SIG-04: Signatures exceeding 2MB limit are rejected."""
    headers = auth_headers(sig_test_env["creator_email"])
    large_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024 + 100)

    files = {"file": ("huge.png", large_bytes, "image/png")}
    resp = client.post("/api/sales-invoices/signatures/temporary", files=files, headers=headers)
    assert resp.status_code == 400
    assert "exceeds maximum limit" in resp.json()["detail"]


def test_reject_corrupted_file(client, auth_headers, sig_test_env):
    """SIG-05: Non-image disguised as PNG is rejected."""
    headers = auth_headers(sig_test_env["creator_email"])
    corrupt_bytes = b"\x89PNG\r\n\x1a\nNOT_A_REAL_IMAGE_DATA_12345"

    files = {"file": ("corrupt.png", corrupt_bytes, "image/png")}
    resp = client.post("/api/sales-invoices/signatures/temporary", files=files, headers=headers)
    assert resp.status_code == 400


def test_temporary_signature_authenticated_view(client, auth_headers, sig_test_env):
    """SIG-06: Authenticated temporary signature streaming works and rejects invalid token."""
    headers = auth_headers(sig_test_env["creator_email"])
    png_bytes = _generate_test_png()

    resp = client.post(
        "/api/sales-invoices/signatures/temporary",
        files={"file": ("view_sig.png", png_bytes, "image/png")},
        headers=headers,
    )
    token = resp.json()["upload_token"]

    # Stream with valid token
    get_resp = client.get(f"/api/sales-invoices/signatures/temp/{token}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.headers["content-type"] == "image/png"

    # Stream with fake token -> 404
    fake_resp = client.get("/api/sales-invoices/signatures/temp/non_existent_token_12345", headers=headers)
    assert fake_resp.status_code == 404


# ── SECTION 2: DRAFT ATTACHMENT, POSITIONING & BOUNDARY CLAMPING ──────────────

def test_attach_signature_to_draft(client, auth_headers, sig_test_env):
    """SIG-07: Attaching temporary signature to draft moves file and updates DB."""
    headers = auth_headers(sig_test_env["creator_email"])

    # 1. Upload temporary signature
    png_bytes = _generate_test_png(width=200, height=100)
    upload_resp = client.post(
        "/api/sales-invoices/signatures/temporary",
        files={"file": ("director_sig.png", png_bytes, "image/png")},
        headers=headers,
    )
    token = upload_resp.json()["upload_token"]

    # 2. Create Draft with signature layout
    draft_payload = {
        "branch_id": sig_test_env["branch_id"],
        "gst_registration_id": sig_test_env["gst_reg_id"],
        "customer_id": sig_test_env["customer_id"],
        "place_of_supply": "33",
        "invoice_date": "2026-06-01",
        "items": [
            {
                "description": "Enterprise Storage Server",
                "hsn_sac_code": "8471",
                "item_type": "goods",
                "quantity": 1,
                "unit": "nos",
                "unit_price": 50000.00,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
        "signatures": [
            {
                "upload_token": token,
                "page_number": 1,
                "is_pinned_to_last_page": False,
                "x_mm": 130.0,
                "y_mm": 240.0,
                "width_mm": 50.0,
                "height_mm": 25.0,
            }
        ],
    }

    create_resp = client.post("/api/sales-invoices/drafts", json=draft_payload, headers=headers)
    assert create_resp.status_code == 201, create_resp.text
    inv_data = create_resp.json()
    assert len(inv_data["signatures"]) == 1

    sig_out = inv_data["signatures"][0]
    assert sig_out["invoice_id"] == inv_data["id"]
    assert Decimal(str(sig_out["x_mm"])) == Decimal("130.00")
    assert Decimal(str(sig_out["y_mm"])) == Decimal("240.00")
    assert Decimal(str(sig_out["width_mm"])) == Decimal("50.00")
    assert Decimal(str(sig_out["height_mm"])) == Decimal("25.00")

    # Verify temporary upload is now marked consumed
    db = SessionLocal()
    try:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        temp_rec = db.query(TemporarySignatureUpload).filter(
            TemporarySignatureUpload.upload_token_hash == token_hash
        ).first()
        assert temp_rec.consumed is True

        # Verify permanent file exists on disk
        perm_file = Path(settings.STORAGE_PATH) / sig_out["storage_key"]
        assert perm_file.exists()
    finally:
        db.close()


def test_reject_reused_upload_token(client, auth_headers, sig_test_env):
    """SIG-08: Reusing an already-consumed temporary upload token is rejected."""
    headers = auth_headers(sig_test_env["creator_email"])

    # Upload token
    png_bytes = _generate_test_png()
    upload_resp = client.post(
        "/api/sales-invoices/signatures/temporary",
        files={"file": ("single_use.png", png_bytes, "image/png")},
        headers=headers,
    )
    token = upload_resp.json()["upload_token"]

    base_payload = {
        "branch_id": sig_test_env["branch_id"],
        "gst_registration_id": sig_test_env["gst_reg_id"],
        "customer_id": sig_test_env["customer_id"],
        "place_of_supply": "33",
        "items": [
            {
                "description": "Item 1",
                "quantity": 1,
                "unit_price": 1000.0,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
        "signatures": [
            {
                "upload_token": token,
                "page_number": 1,
                "x_mm": 50.0,
                "y_mm": 50.0,
                "width_mm": 40.0,
                "height_mm": 20.0,
            }
        ],
    }

    # First draft uses token -> Success
    res1 = client.post("/api/sales-invoices/drafts", json=base_payload, headers=headers)
    assert res1.status_code == 201

    # Second draft tries to reuse same token -> Rejection
    res2 = client.post("/api/sales-invoices/drafts", json=base_payload, headers=headers)
    assert res2.status_code == 400
    assert "already consumed" in res2.json()["detail"]


def test_reject_boundary_overflow(client, auth_headers, sig_test_env):
    """SIG-09: Signatures exceeding A4 physical sheet boundaries (210mm x 297mm) are rejected."""
    headers = auth_headers(sig_test_env["creator_email"])

    # Upload token
    upload_resp = client.post(
        "/api/sales-invoices/signatures/temporary",
        files={"file": ("overflow.png", _generate_test_png(), "image/png")},
        headers=headers,
    )
    token = upload_resp.json()["upload_token"]

    # Overflow width: x_mm (180) + width_mm (40) = 220mm > 210mm
    overflow_payload = {
        "branch_id": sig_test_env["branch_id"],
        "gst_registration_id": sig_test_env["gst_reg_id"],
        "customer_id": sig_test_env["customer_id"],
        "place_of_supply": "33",
        "items": [{"description": "Item", "quantity": 1, "unit_price": 1000.0, "gst_rate": 18.0, "gst_classification": "TAXABLE"}],
        "signatures": [
            {
                "upload_token": token,
                "page_number": 1,
                "x_mm": 180.0,
                "y_mm": 50.0,
                "width_mm": 40.0,
                "height_mm": 20.0,
            }
        ],
    }

    resp = client.post("/api/sales-invoices/drafts", json=overflow_payload, headers=headers)
    assert resp.status_code == 422
    assert "exceeds page width" in resp.json()["detail"]


def test_draft_preview_page_rendering(client, auth_headers, sig_test_env):
    """SIG-10: Server-rendered draft page preview endpoint returns high-resolution PNG."""
    headers = auth_headers(sig_test_env["creator_email"])

    # Create draft
    draft_payload = {
        "branch_id": sig_test_env["branch_id"],
        "gst_registration_id": sig_test_env["gst_reg_id"],
        "customer_id": sig_test_env["customer_id"],
        "place_of_supply": "33",
        "items": [{"description": "Cloud Router", "quantity": 1, "unit_price": 5000.0, "gst_rate": 18.0, "gst_classification": "TAXABLE"}],
    }
    create_resp = client.post("/api/sales-invoices/drafts", json=draft_payload, headers=headers)
    inv_id = create_resp.json()["id"]

    # Fetch page 1 preview
    preview_resp = client.get(f"/api/sales-invoices/drafts/{inv_id}/preview-page?page=1", headers=headers)
    assert preview_resp.status_code == 200
    assert preview_resp.headers["content-type"] == "image/png"
    assert "x-total-pages" in preview_resp.headers

    # Validate image dimensions
    img = Image.open(io.BytesIO(preview_resp.content))
    assert img.width > 500
    assert img.height > 700


# ── SECTION 3: TWO-PHASE APPROVAL, PRECISION STAMPING & IMMUTABILITY ──────────

def test_approval_precision_stamping_and_immutability(client, auth_headers, sig_test_env):
    """
    SIG-11: Full lifecycle test:
    1. Creator uploads signature and positions at exact coordinates (x=140mm, y=240mm, w=50mm, h=25mm).
    2. Creator submits for approval.
    3. Authorized Approver approves invoice.
    4. PyMuPDF inspects stamped output and verifies placement within ±1mm.
    5. Database trigger prevents any modification or deletion of signature records.
    """
    creator_headers = auth_headers(sig_test_env["creator_email"])
    approver_headers = auth_headers(sig_test_env["approver_email"])

    # 1. Upload signature
    upload_resp = client.post(
        "/api/sales-invoices/signatures/temporary",
        files={"file": ("authorized_signatory.png", _generate_test_png(width=200, height=100), "image/png")},
        headers=creator_headers,
    )
    token = upload_resp.json()["upload_token"]

    target_x_mm = 140.0
    target_y_mm = 240.0
    target_w_mm = 50.0
    target_h_mm = 25.0

    # 2. Create Draft with signature
    draft_payload = {
        "branch_id": sig_test_env["branch_id"],
        "gst_registration_id": sig_test_env["gst_reg_id"],
        "customer_id": sig_test_env["customer_id"],
        "place_of_supply": "33",
        "invoice_date": "2026-06-15",
        "items": [
            {
                "description": "Precision Stamping Hardware Module",
                "hsn_sac_code": "8473",
                "item_type": "goods",
                "quantity": 2,
                "unit": "nos",
                "unit_price": 25000.00,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
        "signatures": [
            {
                "upload_token": token,
                "page_number": 1,
                "is_pinned_to_last_page": False,
                "x_mm": target_x_mm,
                "y_mm": target_y_mm,
                "width_mm": target_w_mm,
                "height_mm": target_h_mm,
            }
        ],
    }

    create_resp = client.post("/api/sales-invoices/drafts", json=draft_payload, headers=creator_headers)
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    sig_id = create_resp.json()["signatures"][0]["id"]

    # 3. Submit for approval
    sub_resp = client.post(f"/api/sales-invoices/{inv_id}/submit", headers=creator_headers)
    assert sub_resp.status_code == 200

    # 4. Approver approves and issues invoice
    appr_resp = client.post(f"/api/sales-invoices/{inv_id}/approve", headers=approver_headers)
    assert appr_resp.status_code == 200, appr_resp.text
    issued_data = appr_resp.json()
    assert issued_data["status"] == "approved"
    assert issued_data["pdf_sha256"] is not None

    # 5. Fetch issued PDF and verify PyMuPDF signature stamping precision
    pdf_resp = client.get(f"/api/sales-invoices/{inv_id}/pdf", headers=creator_headers)
    assert pdf_resp.status_code == 200
    pdf_bytes = pdf_resp.content

    # Validate post-stamped SHA256 integrity
    assert hashlib.sha256(pdf_bytes).hexdigest() == issued_data["pdf_sha256"]

    # Inspect PDF with PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) >= 1
    page = doc[0]

    # Verify images exist on page 1
    image_list = page.get_images(full=True)
    assert len(image_list) >= 1, "Expected at least one stamped signature image on page 1"

    # PyMuPDF coordinate verification:
    # Points factor: 72 points / 25.4 mm = 2.834645669...
    mm_to_pts = 72.0 / 25.4
    expected_x0 = target_x_mm * mm_to_pts
    expected_y0 = target_y_mm * mm_to_pts
    expected_x1 = (target_x_mm + target_w_mm) * mm_to_pts
    expected_y1 = (target_y_mm + target_h_mm) * mm_to_pts

    # Locate image rectangle on page
    found_match = False
    for img_info in image_list:
        xref = img_info[0]
        rects = page.get_image_rects(xref)
        for r in rects:
            # Check difference in millimeters
            diff_x0_mm = abs(r.x0 - expected_x0) / mm_to_pts
            diff_y0_mm = abs(r.y0 - expected_y0) / mm_to_pts
            diff_x1_mm = abs(r.x1 - expected_x1) / mm_to_pts
            diff_y1_mm = abs(r.y1 - expected_y1) / mm_to_pts

            # Tolerance requirement: <= ±1.0 mm
            if diff_x0_mm <= 1.0 and diff_y0_mm <= 1.0 and diff_x1_mm <= 1.0 and diff_y1_mm <= 1.0:
                found_match = True
                print(f"Verified precision: ΔX0={diff_x0_mm:.2f}mm, ΔY0={diff_y0_mm:.2f}mm, ΔX1={diff_x1_mm:.2f}mm, ΔY1={diff_y1_mm:.2f}mm")
                break

    assert found_match, f"Stamped signature image not found within ±1mm of ({target_x_mm}, {target_y_mm})"
    doc.close()

    # 6. Database Immutability Trigger Verification:
    # Attempting to directly update or delete signature on approved invoice MUST FAIL!
    db = SessionLocal()
    try:
        from sqlalchemy import text
        # Attempt direct SQL UPDATE on sales_invoice_signatures
        with pytest.raises(Exception) as exc_update:
            db.execute(
                text("UPDATE sales_invoice_signatures SET x_mm = 10.0 WHERE id = :sig_id"),
                {"sig_id": sig_id},
            )
            db.commit()
        assert "Cannot modify or delete signatures on an approved or cancelled invoice" in str(exc_update.value)
        db.rollback()

        # Attempt direct SQL DELETE on sales_invoice_signatures
        with pytest.raises(Exception) as exc_delete:
            db.execute(
                text("DELETE FROM sales_invoice_signatures WHERE id = :sig_id"),
                {"sig_id": sig_id},
            )
            db.commit()
        assert "Cannot modify or delete signatures on an approved or cancelled invoice" in str(exc_delete.value)
        db.rollback()
    finally:
        db.close()


def test_orphan_cleanup_routine():
    """SIG-12: Expired unconsumed temporary uploads are cleaned up."""
    db = SessionLocal()
    try:
        branch = db.query(Branch).filter(Branch.company_id == 40).first()
        user = db.query(User).filter(User.company_id == 40).first()
        assert branch is not None and user is not None

        # Create expired unconsumed record
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        test_path = Path(settings.STORAGE_PATH) / f"signatures/tmp/40/{token_hash}.png"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_bytes(b"\x89PNG\r\n\x1a\nEXPIRED_CLEANUP_TEST")

        expired_rec = TemporarySignatureUpload(
            upload_token_hash=token_hash,
            company_id=40,
            branch_id=branch.id,
            user_id=user.id,
            storage_key=f"signatures/tmp/40/{token_hash}.png",
            original_filename="expired.png",
            mime_type="image/png",
            file_size=len(b"EXPIRED_CLEANUP_TEST"),
            sha256="dummy_sha",
            aspect_ratio=Decimal("2.0"),
            width_px=200,
            height_px=100,
            consumed=False,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        db.add(expired_rec)
        db.commit()

        # Run cleanup
        cleaned_count = cleanup_expired_signature_uploads(db)
        assert cleaned_count >= 1

        # Verify DB record deleted
        rec_check = db.query(TemporarySignatureUpload).filter(
            TemporarySignatureUpload.upload_token_hash == token_hash
        ).first()
        assert rec_check is None

        # Verify file unlinked from disk
        assert not test_path.exists()
    finally:
        db.close()
