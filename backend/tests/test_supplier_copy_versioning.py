"""
Tests for Module 13 Phase 6: Supplier Copy Versioning & Stale Detection.
- Document 492 / Invoice 106 baseline preservation.
- Stale detection after structured data edits.
- Regeneration as new version (v1 -> v2) without overwriting historical PDFs.
- Historical version retrieval.
- 30-day cutoff enforcement on supplier copy access.
"""

from datetime import datetime, timedelta, timezone
import json
import pytest
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import Document, Invoice, SupplierInvoiceCopy, User, UserRole, OcrStatus
from app.services.supplier_copy_service import (
    compute_source_data_hash,
    check_supplier_copy_stale,
    get_current_supplier_copy,
)


def test_document_492_baseline_preservation(client, auth_headers):
    """Verifies live Document 492 and Invoice 106 copy version 1 are intact and not stale."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == 492).first()
        assert doc is not None

        copy = get_current_supplier_copy(db, 492)
        assert copy is not None
        assert copy.copy_version == 1
        assert copy.is_current is True
        assert copy.invoice_id == 106
        assert copy.pdf_sha256 == "733c6cc69db11d086f76415a2459dfa42c8b5fddc0665f10671e3d9f720e635a"

        # Check stale detection
        is_stale = check_supplier_copy_stale(db, doc)
        assert is_stale is False
    finally:
        db.close()


def test_stale_detection_and_regeneration(client, auth_headers):
    """
    Simulates human OCR verification edit on a test document, verifies stale detection,
    regenerates version 2, and verifies version 1 PDF is preserved intact.
    """
    import uuid
    db = SessionLocal()
    test_run_id = uuid.uuid4().hex[:8]
    try:
        user = db.query(User).filter(User.email == "jayasri@example.com").first()
        # Create a test document with initial structured data
        doc = Document(
            company_id=user.company_id,
            branch_id=user.branch_id,
            uploaded_by=user.id,
            original_filename=f"supplier_test_invoice_{test_run_id}.jpg",
            storage_key=f"supplier_test_invoice_{test_run_id}.jpg",
            mime_type="image/jpeg",
            file_size=1024,
            sha256=f"testsha256_{test_run_id}",
            ocr_status=OcrStatus.COMPLETED,
            ocr_text="Tax Invoice lucky computers 96000",
            structured_data=json.dumps({
                "seller": {"name": "Test Supplier Ltd", "gstin": "33BLAPS0819R1ZQ"},
                "invoice": {"number": "SUPP-001", "date": "10-May-2026"},
                "totals": {"grand_total": 5000.00},
            }, sort_keys=True),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        headers = auth_headers("jayasri@example.com")

        # 1. First generation via endpoint
        resp1 = client.get(f"/api/documents/{doc.id}/invoice.pdf", headers=headers)
        assert resp1.status_code == 200

        # Check that version 1 record exists
        copy1 = get_current_supplier_copy(db, doc.id)
        assert copy1 is not None
        assert copy1.copy_version == 1
        assert copy1.is_current is True
        assert copy1.pdf_storage_key == f"generated_invoice_{doc.id}.pdf"
        v1_filename = copy1.pdf_storage_key
        v1_sha = copy1.pdf_sha256

        # Verify initial state is NOT stale
        assert check_supplier_copy_stale(db, doc) is False

        # 2. Simulate human correction to structured data
        updated_data = json.loads(doc.structured_data)
        updated_data["totals"]["grand_total"] = 6500.00
        doc.structured_data = json.dumps(updated_data, sort_keys=True)
        db.commit()

        # 3. Verify stale detection detects change
        assert check_supplier_copy_stale(db, doc) is True

        # Check GET /api/documents/{doc_id}/copies reports stale
        resp_copies = client.get(f"/api/documents/{doc.id}/copies", headers=headers)
        assert resp_copies.status_code == 200
        copies_list = resp_copies.json()
        assert len(copies_list) == 1
        assert copies_list[0]["is_stale"] is True

        # 4. Regenerate copy as version 2
        regen_resp = client.post(f"/api/documents/{doc.id}/copies/regenerate", headers=headers)
        assert regen_resp.status_code == 200
        regen_data = regen_resp.json()
        assert regen_data["copy_version"] == 2
        assert regen_data["is_current"] is True
        assert regen_data["pdf_filename"] == f"generated_invoice_{doc.id}_v2.pdf"

        # 5. Verify database records
        db.refresh(doc)
        db.expire_all()
        all_copies = (
            db.query(SupplierInvoiceCopy)
            .filter(SupplierInvoiceCopy.document_id == doc.id)
            .order_by(SupplierInvoiceCopy.copy_version.asc())
            .all()
        )
        assert len(all_copies) == 2
        # Version 1 is retained and marked not current
        assert all_copies[0].copy_version == 1
        assert all_copies[0].is_current is False
        assert all_copies[0].pdf_storage_key == v1_filename

        # Version 2 is now current and not stale
        assert all_copies[1].copy_version == 2
        assert all_copies[1].is_current is True
        assert check_supplier_copy_stale(db, doc) is False

        # 6. Verify historical PDF files both exist and are accessible
        resp_v1_pdf = client.get(f"/api/documents/{doc.id}/copies/1/pdf", headers=headers)
        assert resp_v1_pdf.status_code == 200

        resp_v2_pdf = client.get(f"/api/documents/{doc.id}/copies/2/pdf", headers=headers)
        assert resp_v2_pdf.status_code == 200

        # Cleanup test document and copies
        db.query(SupplierInvoiceCopy).filter(SupplierInvoiceCopy.document_id == doc.id).delete()
        db.query(Invoice).filter(Invoice.document_id == doc.id).delete()
        db.query(Document).filter(Document.id == doc.id).delete()
        db.commit()
    finally:
        db.close()


def test_supplier_copy_30_day_cutoff_for_staff(client, auth_headers):
    """Staff user cannot access supplier invoice copy of a document created > 30 days ago."""
    import uuid
    db = SessionLocal()
    cutoff_run_id = uuid.uuid4().hex[:8]
    try:
        staff = db.query(User).filter(User.email == "sujipriya@example.com").first()
        old_created = datetime.now(timezone.utc) - timedelta(days=35)

        old_doc = Document(
            company_id=staff.company_id,
            branch_id=staff.branch_id,
            uploaded_by=staff.id,
            original_filename=f"old_invoice_{cutoff_run_id}.jpg",
            storage_key=f"old_invoice_{cutoff_run_id}.jpg",
            mime_type="image/jpeg",
            file_size=1024,
            sha256=f"oldsha256_{cutoff_run_id}",
            ocr_status=OcrStatus.COMPLETED,
            ocr_text="Tax invoice past 30 days",
            structured_data=json.dumps({"totals": {"grand_total": 1000.0}}),
            created_at=old_created,
        )
        db.add(old_doc)
        db.flush()

        old_inv = Invoice(
            document_id=old_doc.id,
            company_id=staff.company_id,
            branch_id=staff.branch_id,
            uploaded_by=staff.id,
            kind="copy",
            status="available",
            grand_total=1000.0,
            currency="INR",
            created_at=old_created,
        )
        db.add(old_inv)
        db.flush()

        old_copy = SupplierInvoiceCopy(
            invoice_id=old_inv.id,
            company_id=staff.company_id,
            document_id=old_doc.id,
            copy_version=1,
            is_current=True,
            is_stale=False,
            source_data_hash=compute_source_data_hash(old_doc.structured_data),
            pdf_storage_key=f"generated_invoice_{old_doc.id}.pdf",
            pdf_sha256="testsha256cutoff123",
            created_at=old_created,
        )
        db.add(old_copy)
        db.commit()

        staff_headers = auth_headers("sujipriya@example.com")
        admin_headers = auth_headers("jayasri@example.com")

        # Staff user past 30 days gets 404 Not Found
        resp_staff = client.get(f"/api/invoices/{old_inv.id}", headers=staff_headers)
        assert resp_staff.status_code == 404

        # Company Admin can access
        resp_admin = client.get(f"/api/invoices/{old_inv.id}", headers=admin_headers)
        assert resp_admin.status_code == 200

        # Cleanup
        db.query(SupplierInvoiceCopy).filter(SupplierInvoiceCopy.id == old_copy.id).delete()
        db.query(Invoice).filter(Invoice.id == old_inv.id).delete()
        db.query(Document).filter(Document.id == old_doc.id).delete()
        db.commit()
    finally:
        db.close()
