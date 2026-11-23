"""
Test suite verifying Invoice Type selection on upload, persistence in database,
filtering across Document search and Invoices repository endpoints, and default handling.
"""

import io
import uuid
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Company, Branch, User, UserRole, AccountStatus, UserRoleAssignment, Document, Invoice
from app.auth import get_password_hash, create_access_token
from app.main import app


def _create_minimal_png(color=(255, 255, 255)):
    img = Image.new("RGB", (100, 100), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def setup_env(db):
    tag = uuid.uuid4().hex[:6]
    co = Company(
        name=f"Invoice Type Corp {tag}",
        code=f"IT_{tag}",
        gstin="33AAAAA0000A1Z5",
    )
    db.add(co)
    db.flush()

    br = Branch(
        company_id=co.id,
        name=f"Main Branch {tag}",
        code=f"BR_{tag}",
    )
    db.add(br)
    db.flush()

    pwd = get_password_hash("Password@123")
    user = User(
        company_id=co.id,
        branch_id=br.id,
        name=f"Admin {tag}",
        email=f"admin_{tag}@example.com",
        password_hash=pwd,
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    db.add(user)
    db.flush()

    ura = UserRoleAssignment(
        user_id=user.id,
        role="GLOBAL_ADMIN",
        scope_type="company",
        scope_id=co.id,
    )
    db.add(ura)
    db.commit()

    token = create_access_token({
        "sub": user.email,
        "user_id": user.id,
        "company_id": co.id,
        "branch_id": br.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
        "token_version": user.token_version,
    }, audience="company")

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    yield {
        "co": co,
        "br": br,
        "user": user,
        "client": client,
        "headers": headers,
    }

    # Teardown
    db.query(Invoice).filter(Invoice.company_id == co.id).delete()
    db.query(Document).filter(Document.company_id == co.id).delete()
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).delete()
    db.query(User).filter(User.company_id == co.id).delete()
    db.query(Branch).filter(Branch.company_id == co.id).delete()
    db.query(Company).filter(Company.id == co.id).delete()
    db.commit()


def test_upload_with_custom_invoice_type(setup_env, db):
    client = setup_env["client"]
    headers = setup_env["headers"]

    file_bytes = _create_minimal_png()

    # Upload single document with "Bill of Supply"
    resp = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("bill_of_supply.png", file_bytes, "image/png")},
        data={"invoice_type": "Bill of Supply"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["invoice_type"] == "Bill of Supply"
    doc_id = data["id"]

    # Verify directly in DB
    doc_in_db = db.query(Document).filter(Document.id == doc_id).first()
    assert doc_in_db is not None
    assert doc_in_db.invoice_type == "Bill of Supply"


def test_upload_default_invoice_type_is_tax_invoice(setup_env):
    client = setup_env["client"]
    headers = setup_env["headers"]

    file_bytes = _create_minimal_png()

    # Upload single document without specifying invoice_type
    resp = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("default_tax_inv.png", file_bytes, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["invoice_type"] == "Tax Invoice"


def test_filter_documents_by_invoice_type(setup_env):
    client = setup_env["client"]
    headers = setup_env["headers"]

    file1 = _create_minimal_png(color=(255, 0, 0))
    file2 = _create_minimal_png(color=(0, 255, 0))

    # Upload 1: Credit Note
    r1 = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("cn.png", file1, "image/png")},
        data={"invoice_type": "Credit Note"},
    )
    assert r1.status_code == 200

    # Upload 2: Debit Note
    r2 = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("dn.png", file2, "image/png")},
        data={"invoice_type": "Debit Note"},
    )
    assert r2.status_code == 200

    # Filter by "Credit Note" on /api/documents
    list_cn = client.get("/api/documents?invoice_type=Credit Note&paginate=true", headers=headers)
    assert list_cn.status_code == 200
    cn_items = list_cn.json()["items"]
    assert len(cn_items) == 1
    assert cn_items[0]["invoice_type"] == "Credit Note"

    # Filter by "Debit Note" on /api/documents/search
    search_dn = client.get("/api/documents/search?invoice_type=Debit Note", headers=headers)
    assert search_dn.status_code == 200
    dn_items = search_dn.json()["items"]
    assert len(dn_items) == 1
    assert dn_items[0]["invoice_type"] == "Debit Note"


def test_filter_invoices_repository_by_invoice_type(setup_env, db):
    client = setup_env["client"]
    headers = setup_env["headers"]
    co = setup_env["co"]
    br = setup_env["br"]
    user = setup_env["user"]

    # Create two invoices directly
    inv1 = Invoice(
        company_id=co.id,
        branch_id=br.id,
        uploaded_by=user.id,
        kind="copy",
        status="available",
        invoice_number="BOS-001",
        invoice_type="Bill of Supply",
    )
    inv2 = Invoice(
        company_id=co.id,
        branch_id=br.id,
        uploaded_by=user.id,
        kind="copy",
        status="available",
        invoice_number="TI-001",
        invoice_type="Tax Invoice",
    )
    db.add_all([inv1, inv2])
    db.commit()

    # Query all
    r_all = client.get("/api/invoices", headers=headers)
    assert r_all.status_code == 200
    assert len(r_all.json()) >= 2

    # Query Bill of Supply
    r_bos = client.get("/api/invoices?invoice_type=Bill of Supply", headers=headers)
    assert r_bos.status_code == 200
    bos_list = r_bos.json()
    assert len(bos_list) == 1
    assert bos_list[0]["invoice_number"] == "BOS-001"
    assert bos_list[0]["invoice_type"] == "Bill of Supply"

    # Query Tax Invoice
    r_ti = client.get("/api/invoices?invoice_type=Tax Invoice", headers=headers)
    assert r_ti.status_code == 200
    ti_list = r_ti.json()
    assert all(inv["invoice_type"] == "Tax Invoice" for inv in ti_list)
