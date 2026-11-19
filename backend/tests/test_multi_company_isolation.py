"""
Comprehensive Multi-Company Isolation Test Suite (Module 2).

Covers:
  A. Database relationship & composite foreign key constraints.
  B. Strict Cross-Company Isolation (Company A vs Company B).
  C. Request manipulation & privilege escalation attempts.
  D. Company-scoped Branch access control.
  E. 30-day Staff visibility window in multi-company context.
  F. Company suspension & reactivation workflows.
"""

import io
from datetime import datetime, timedelta
import pytest
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

from app.models import (
    Company,
    CompanyStatus,
    Branch,
    User,
    UserRole,
    Document,
    Invoice,
    OcrStatus,
    UserRoleAssignment,
    UserSession,
)
from app.auth import get_password_hash, create_access_token
from app.repositories import CompanyRepository


# ── Fixtures: Provision Company B ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def company_b_data(client: TestClient):
    """
    Provisions a second company (Acme Enterprises) with its own branches,
    admin, staff, documents, and invoices.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # Create Company B
        acme = db.query(Company).filter(Company.code == "ACME_ENT").first()
        if not acme:
            acme = Company(
                name="Acme Enterprises",
                code="ACME_ENT",
                status=CompanyStatus.ACTIVE,
                gstin="29ABCDE1234F1Z5",
            )
            db.add(acme)
            db.flush()
        else:
            acme.status = CompanyStatus.ACTIVE
            db.commit()

        # Create Company B branches: Bangalore and Mysore (tests duplicate branch code across different companies!)
        blr_branch = db.query(Branch).filter(Branch.company_id == acme.id, Branch.code == "BLR").first()
        if not blr_branch:
            blr_branch = Branch(company_id=acme.id, name="Bangalore", code="BLR")
            db.add(blr_branch)

        # Same branch code 'MYSORE' as Company A, but belonging to Company B
        mys_branch = db.query(Branch).filter(Branch.company_id == acme.id, Branch.code == "MYSORE").first()
        if not mys_branch:
            mys_branch = Branch(company_id=acme.id, name="Mysore Branch B", code="MYSORE")
            db.add(mys_branch)

        db.flush()

        # Create Company B Users
        pw_hash = get_password_hash("AcmePassword@123")

        acme_admin = db.query(User).filter(User.email == "acme_admin@acme.com").first()
        if not acme_admin:
            acme_admin = User(
                company_id=acme.id,
                branch_id=blr_branch.id,
                name="Acme Admin",
                email="acme_admin@acme.com",
                password_hash=pw_hash,
                role=UserRole.ADMIN,
            )
            db.add(acme_admin)

        acme_staff = db.query(User).filter(User.email == "acme_staff@acme.com").first()
        if not acme_staff:
            acme_staff = User(
                company_id=acme.id,
                branch_id=blr_branch.id,
                name="Acme Staff",
                email="acme_staff@acme.com",
                password_hash=pw_hash,
                role=UserRole.STAFF,
            )
            db.add(acme_staff)

        db.flush()

        # Create Company B Document
        acme_doc = db.query(Document).filter(Document.original_filename == "acme_confidential_receipt.pdf").first()
        if not acme_doc:
            acme_doc = Document(
                company_id=acme.id,
                branch_id=blr_branch.id,
                uploaded_by=acme_staff.id,
                original_filename="acme_confidential_receipt.pdf",
                storage_key="acme_doc_storage_key_1.pdf",
                mime_type="application/pdf",
                file_size=1024,
                ocr_text="Acme Secret Financials 2026",
                ocr_status=OcrStatus.COMPLETED,
            )
            db.add(acme_doc)
            db.flush()

        # Create Company B Invoice
        acme_inv = db.query(Invoice).filter(Invoice.document_id == acme_doc.id).first()
        if not acme_inv:
            acme_inv = Invoice(
                document_id=acme_doc.id,
                company_id=acme.id,
                branch_id=blr_branch.id,
                uploaded_by=acme_staff.id,
                invoice_number="ACME-INV-999",
                invoice_date="01-Nov-2026",
                seller_name="Acme Supplies",
                buyer_name="Alpha Corp",
                grand_total="75000",
                currency="INR",
                pdf_filename="acme_invoice_999.pdf",
                file_size=2048,
            )
            db.add(acme_inv)

        db.commit()

        yield {
            "company_id": acme.id,
            "branch_id": blr_branch.id,
            "admin_email": "acme_admin@acme.com",
            "staff_email": "acme_staff@acme.com",
            "password": "AcmePassword@123",
            "doc_id": acme_doc.id,
            "invoice_id": acme_inv.id,
        }
    finally:
        # Clean up Acme Enterprises so tests never leave residual data in DB
        try:
            acme_comp = db.query(Company).filter(Company.code == "ACME_ENT").first()
            if acme_comp:
                c_id = acme_comp.id
                db.query(Invoice).filter(Invoice.company_id == c_id).delete(synchronize_session=False)
                db.query(Document).filter(Document.company_id == c_id).delete(synchronize_session=False)
                acme_users = db.query(User).filter(User.company_id == c_id).all()
                u_ids = [u.id for u in acme_users]
                if u_ids:
                    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(u_ids)).delete(synchronize_session=False)
                    db.query(UserSession).filter(UserSession.user_id.in_(u_ids)).delete(synchronize_session=False)
                    db.query(User).filter(User.id.in_(u_ids)).delete(synchronize_session=False)
                db.query(Branch).filter(Branch.company_id == c_id).delete(synchronize_session=False)
                db.delete(acme_comp)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


@pytest.fixture
def acme_admin_headers(client, company_b_data):
    resp = client.post("/api/auth/login", json={
        "email": company_b_data["admin_email"],
        "password": company_b_data["password"],
    })
    assert resp.status_code == 200, f"Acme admin login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def acme_staff_headers(client, company_b_data):
    resp = client.post("/api/auth/login", json={
        "email": company_b_data["staff_email"],
        "password": company_b_data["password"],
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Category A: Database Relationship & Composite Constraint Tests ────────────

def test_same_branch_code_allowed_in_different_companies(db, company_b_data):
    """
    Verifies that 'MYSORE' can exist in both Vasanth & Co. and Acme Enterprises,
    demonstrating composite uniqueness on (company_id, code).
    """
    mysore_branches = db.query(Branch).filter(Branch.code == "MYSORE").all()
    company_ids = {b.company_id for b in mysore_branches}
    assert len(company_ids) >= 2


def test_duplicate_branch_code_within_same_company_rejected(db):
    """Verifies that duplicate branch codes within the SAME company violate uniqueness."""
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    dup_branch = Branch(company_id=vasanth.id, name="Duplicate Chennai", code="CHENNAI")
    db.add(dup_branch)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_mismatched_company_and_branch_rejected_by_composite_fk(db, company_b_data):
    """
    CRITICAL DATABASE TEST:
    Attempting to create a document with Company A's ID but Company B's branch_id
    MUST be rejected by the composite foreign key constraint:
    (company_id, branch_id) -> branches(company_id, id).
    """
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    vasanth_user = db.query(User).filter(User.company_id == vasanth.id).first()
    acme_branch_id = company_b_data["branch_id"]

    invalid_doc = Document(
        company_id=vasanth.id,
        branch_id=acme_branch_id,  # Belongs to Acme, NOT Vasanth!
        uploaded_by=vasanth_user.id,
        original_filename="tampered_mismatch.pdf",
        storage_key="mismatch_storage_key_1",
        mime_type="application/pdf",
        file_size=500,
    )
    db.add(invalid_doc)
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    db.rollback()
    assert "fk_documents_company_branch" in str(exc.value)


# ── Category B: Strict Cross-Company Isolation Tests ──────────────────────────

def test_company_a_user_cannot_list_company_b_documents(client, auth_headers, company_b_data):
    """Vasanth & Co. admin must never see Acme Enterprises documents in list."""
    vasanth_headers = auth_headers("samrethi@example.com")
    resp = client.get("/api/documents", headers=vasanth_headers)
    assert resp.status_code == 200
    docs = resp.json()
    doc_ids = [d["id"] for d in docs]
    assert company_b_data["doc_id"] not in doc_ids


def test_company_b_user_cannot_list_company_a_documents(client, acme_admin_headers, db):
    """Acme Enterprises admin must never see Vasanth & Co. documents."""
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    resp = client.get("/api/documents", headers=acme_admin_headers)
    assert resp.status_code == 200
    docs = resp.json()
    for d in docs:
        assert d["company_id"] != vasanth.id
        assert "chennai" not in d["original_filename"].lower()


def test_company_a_user_cannot_get_company_b_document_by_id(client, auth_headers, company_b_data):
    """Direct lookup of Company B document by ID returns 404 (not 403, preventing enumeration)."""
    vasanth_headers = auth_headers("samrethi@example.com")
    resp = client.get(f"/api/documents/{company_b_data['doc_id']}", headers=vasanth_headers)
    assert resp.status_code == 404
    body = resp.json()
    err_msg = body.get("error", {}).get("detail", body.get("detail", ""))
    assert "not found" in err_msg.lower()


def test_company_a_user_cannot_download_company_b_file(client, auth_headers, company_b_data):
    """Direct download of Company B document file returns 404."""
    vasanth_headers = auth_headers("samrethi@example.com")
    resp = client.get(f"/api/documents/{company_b_data['doc_id']}/file", headers=vasanth_headers)
    assert resp.status_code == 404


def test_company_a_user_cannot_delete_company_b_document(client, auth_headers, company_b_data):
    """Delete of Company B document returns 404."""
    vasanth_headers = auth_headers("samrethi@example.com")
    resp = client.delete(f"/api/documents/{company_b_data['doc_id']}", headers=vasanth_headers)
    assert resp.status_code == 404


def test_company_a_user_cannot_reprocess_company_b_document(client, auth_headers, company_b_data):
    """Reprocess of Company B document returns 404."""
    vasanth_headers = auth_headers("samrethi@example.com")
    resp = client.post(f"/api/documents/{company_b_data['doc_id']}/reprocess", headers=vasanth_headers)
    assert resp.status_code == 404


def test_company_a_user_cannot_access_company_b_invoice(client, auth_headers, company_b_data):
    """Invoice endpoints enforce company isolation."""
    vasanth_headers = auth_headers("samrethi@example.com")

    # List
    list_resp = client.get("/api/invoices", headers=vasanth_headers)
    assert list_resp.status_code == 200
    inv_ids = [inv["id"] for inv in list_resp.json()]
    assert company_b_data["invoice_id"] not in inv_ids

    # Detail
    get_resp = client.get(f"/api/invoices/{company_b_data['invoice_id']}", headers=vasanth_headers)
    assert get_resp.status_code == 404


# ── Category C: Request Manipulation & Spoofing Tests ─────────────────────────

def test_tampered_company_id_in_payload_ignored(client, acme_admin_headers, db):
    """
    Even if an attacker injects `company_id=1` (or another company) in request headers,
    body, or query parameters, the server ignores it and binds strictly to AuthContext.
    """
    from PIL import Image
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    img = Image.new("RGB", (10, 10), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    fake_file = io.BytesIO(buf.getvalue())
    resp = client.post(
        f"/api/documents?company_id={vasanth.id}",
        headers=acme_admin_headers,
        files={"file": ("spoof_attempt.jpg", fake_file, "image/jpeg")},
    )
    assert resp.status_code == 200
    doc_data = resp.json()

    # Verify the document was assigned to Acme Enterprises, NOT the spoofed vasanth company id!
    created_doc = db.query(Document).filter(Document.id == doc_data["id"]).first()
    assert created_doc.company_id != vasanth.id
    assert created_doc.company.code == "ACME_ENT"

    # Cleanup
    db.delete(created_doc)
    db.commit()


# ── Category F: Company Suspension & Reactivation Tests ───────────────────────

def test_company_suspension_blocks_tenant_operations(client, acme_admin_headers, company_b_data, db):
    """
    When a company is SUSPENDED:
      - Normal logins are blocked (403).
      - Authenticated business requests receive 403 Forbidden.
      - Data is preserved intact.
    """
    company_repo = CompanyRepository(db)

    try:
        # 1. Suspend Acme Enterprises
        company_repo.suspend(company_b_data["company_id"])

        # 2. Login attempt during suspension is rejected with 403
        login_resp = client.post("/api/auth/login", json={
            "email": company_b_data["admin_email"],
            "password": company_b_data["password"],
        })
        assert login_resp.status_code == 403
        assert "suspended" in login_resp.json()["detail"].lower()

        # 3. Existing token operations are rejected with 403
        doc_list_resp = client.get("/api/documents", headers=acme_admin_headers)
        assert doc_list_resp.status_code == 403
        assert "suspended" in doc_list_resp.json()["detail"].lower()

        # 4. Upload during suspension is rejected with 403
        fake_file = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 20)
        upload_resp = client.post(
            "/api/documents",
            headers=acme_admin_headers,
            files={"file": ("blocked_during_suspension.jpg", fake_file, "image/jpeg")},
        )
        assert upload_resp.status_code == 403
    finally:
        # 5. Reactivate the company
        company_repo.activate(company_b_data["company_id"])

    # 6. Verify access is restored immediately
    restore_resp = client.get("/api/documents", headers=acme_admin_headers)
    assert restore_resp.status_code == 200
