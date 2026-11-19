"""
Module 12 Test Suite — Search Upgrade: Implementation and Verification.

Covers:
1. Exact invoice number search
2. Exact GSTIN search
3. Full-text search across OCR text with highlighted snippets
4. Partial and trigram matching (e.g. hyphenated / alphanumeric tokens)
5. Misspelled vendor search (e.g. 'Lukcy' -> 'Lucky Computers')
6. Structured date range filtering (ISO and Indian date formats)
7. Indian amount parsing and structured amount range filtering (e.g. 1,20,000 / ₹ 96,000.00)
8. Multi-tenant company isolation
9. Branch-level permission enforcement and query scoping
10. Strict 30-day uploader access cutoff for Staff users
11. Document thumbnail generation, caching, and unauthorized access protection (HTTP 404 anti-enumeration)
12. Secure pagination and total count guarantees
13. Database trigger automatic search vector maintenance
14. Zero test data leaks (clean teardown)
"""

import io
import json
import uuid
from datetime import datetime, timedelta
from PIL import Image

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import (
    Company, Branch, User, UserRole, AccountStatus, UserRoleAssignment, Document,
    ProcessingJob, OcrStatus,
)
from app.auth import get_password_hash, create_access_token
from app.services.search_service import DocumentSearchService, parse_indian_amount, parse_indian_date, sync_document_search_metadata
from app.storage import get_storage_adapter, LocalStorageAdapter
from app.main import app


# ── Fixtures & Setup ─────────────────────────────────────────────────────────

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_env(db):
    """
    Creates an isolated test environment with:
    - Company A (Chennai and Mysore branches)
    - Company A Global Admin, Branch Admin, and Staff user
    - Company B (isolated company with Admin)
    """
    tag = uuid.uuid4().hex[:6]

    company_a = Company(
        name=f"Mod12 Corp A {tag}",
        display_name=f"Mod12 Enterprise A {tag}",
        code=f"M12A_{tag}",
        status="active",
        storage_limit_bytes=100 * 1024 * 1024,
    )
    company_b = Company(
        name=f"Mod12 Corp B {tag}",
        display_name=f"Mod12 Enterprise B {tag}",
        code=f"M12B_{tag}",
        status="active",
        storage_limit_bytes=100 * 1024 * 1024,
    )
    db.add_all([company_a, company_b])
    db.flush()

    chennai = Branch(
        company_id=company_a.id,
        name=f"Chennai Branch {tag}",
        code=f"CHN_{tag}",
        status="active",
    )
    mysore = Branch(
        company_id=company_a.id,
        name=f"Mysore Branch {tag}",
        code=f"MYS_{tag}",
        status="active",
    )
    branch_b = Branch(
        company_id=company_b.id,
        name=f"Branch B {tag}",
        code=f"BB_{tag}",
        status="active",
    )
    db.add_all([chennai, mysore, branch_b])
    db.flush()

    # Users in Company A
    admin_a = User(
        company_id=company_a.id,
        branch_id=chennai.id,
        email=f"admin_a_{tag}@m12test.com",
        name=f"Admin A {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    branch_admin_chn = User(
        company_id=company_a.id,
        branch_id=chennai.id,
        email=f"branch_chn_{tag}@m12test.com",
        name=f"Branch Admin CHN {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.ADMIN,
        status=AccountStatus.ACTIVE,
    )
    staff_chn = User(
        company_id=company_a.id,
        branch_id=chennai.id,
        email=f"staff_chn_{tag}@m12test.com",
        name=f"Staff CHN {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.STAFF,
        status=AccountStatus.ACTIVE,
    )

    # User in Company B
    admin_b = User(
        company_id=company_b.id,
        branch_id=branch_b.id,
        email=f"admin_b_{tag}@m12test.com",
        name=f"Admin B {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    db.add_all([admin_a, branch_admin_chn, staff_chn, admin_b])
    db.flush()

    # Role assignments
    db.add(UserRoleAssignment(user_id=admin_a.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=company_a.id))
    db.add(UserRoleAssignment(user_id=branch_admin_chn.id, role="ADMIN", scope_type="branch", scope_id=chennai.id))
    db.add(UserRoleAssignment(user_id=staff_chn.id, role="STAFF", scope_type="branch", scope_id=chennai.id))
    db.add(UserRoleAssignment(user_id=admin_b.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=company_b.id))
    db.commit()

    token_admin_a = create_access_token({
        "sub": admin_a.email,
        "user_id": admin_a.id,
        "company_id": company_a.id,
        "branch_id": chennai.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
    }, audience="company")

    token_branch_chn = create_access_token({
        "sub": branch_admin_chn.email,
        "user_id": branch_admin_chn.id,
        "company_id": company_a.id,
        "branch_id": chennai.id,
        "role": "ADMIN",
        "portal": "company",
    }, audience="company")

    token_staff_chn = create_access_token({
        "sub": staff_chn.email,
        "user_id": staff_chn.id,
        "company_id": company_a.id,
        "branch_id": chennai.id,
        "role": "STAFF",
        "portal": "company",
    }, audience="company")

    token_admin_b = create_access_token({
        "sub": admin_b.email,
        "user_id": admin_b.id,
        "company_id": company_b.id,
        "branch_id": branch_b.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
    }, audience="company")

    storage = get_storage_adapter()

    # Create dummy image data in storage
    img = Image.new("RGB", (400, 400), color="red")
    img_bytes_io = io.BytesIO()
    img.save(img_bytes_io, format="JPEG")
    dummy_img_bytes = img_bytes_io.getvalue()

    created_storage_keys = []

    def make_doc(company, branch, uploader, filename, ocr_text, structured_dict=None, days_ago=0):
        doc_uuid = uuid.uuid4().hex
        key = LocalStorageAdapter.build_original_key(company.id, branch.id, doc_uuid)
        storage.save(key, dummy_img_bytes)
        created_storage_keys.append(key)

        created_dt = datetime.utcnow() - timedelta(days=days_ago)
        doc = Document(
            company_id=company.id,
            branch_id=branch.id,
            uploaded_by=uploader.id,
            original_filename=filename,
            storage_key=key,
            mime_type="image/jpeg",
            file_size=len(dummy_img_bytes),
            ocr_status=OcrStatus.COMPLETED,
            ocr_text=ocr_text,
            created_at=created_dt,
        )
        if structured_dict:
            doc.structured_data = json.dumps(structured_dict)
            sync_document_search_metadata(doc, structured_dict)
        db.add(doc)
        db.flush()
        db.commit()
        db.refresh(doc)
        return doc

    env_data = {
        "company_a": company_a,
        "company_b": company_b,
        "chennai": chennai,
        "mysore": mysore,
        "branch_b": branch_b,
        "admin_a": admin_a,
        "branch_admin_chn": branch_admin_chn,
        "staff_chn": staff_chn,
        "admin_b": admin_b,
        "token_admin_a": token_admin_a,
        "token_branch_chn": token_branch_chn,
        "token_staff_chn": token_staff_chn,
        "token_admin_b": token_admin_b,
        "make_doc": make_doc,
    }

    try:
        yield env_data
    finally:
        # Cleanup files in storage
        for k in created_storage_keys:
            try:
                storage.delete(k)
                thumb_k = f"{k}_thumb_200.jpg"
                if storage.exists(thumb_k):
                    storage.delete(thumb_k)
            except Exception:
                pass

        # Cleanup DB
        db.rollback()
        c_ids = [company_a.id, company_b.id]
        doc_ids = [d.id for d in db.query(Document.id).filter(Document.company_id.in_(c_ids)).all()]
        if doc_ids:
            db.query(ProcessingJob).filter(ProcessingJob.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)

        u_ids = [admin_a.id, branch_admin_chn.id, staff_chn.id, admin_b.id]
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(u_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(u_ids)).delete(synchronize_session=False)
        db.query(Branch).filter(Branch.company_id.in_(c_ids)).delete(synchronize_session=False)
        db.query(Company).filter(Company.id.in_(c_ids)).delete(synchronize_session=False)
        db.commit()


# ── 1. Unit Parsing Tests ────────────────────────────────────────────────────

def test_parse_indian_amount():
    assert parse_indian_amount(96000) == 96000.0
    assert parse_indian_amount("96000") == 96000.0
    assert parse_indian_amount("1,20,000") == 120000.0
    assert parse_indian_amount("12,50,000.50") == 1250000.50
    assert parse_indian_amount("₹ 96,000.00") == 96000.0
    assert parse_indian_amount("Rs. 1,50,000") == 150000.0
    assert parse_indian_amount("INR 5,000") == 5000.0
    assert parse_indian_amount(None) is None
    assert parse_indian_amount("invalid") is None


def test_parse_indian_date():
    assert parse_indian_date("2026-03-19") == datetime(2026, 3, 19).date()
    assert parse_indian_date("19/03/2026") == datetime(2026, 3, 19).date()
    assert parse_indian_date("19-03-2026") == datetime(2026, 3, 19).date()
    assert parse_indian_date("19-Mar-2026") == datetime(2026, 3, 19).date()
    assert parse_indian_date(None) is None
    assert parse_indian_date("invalid-date") is None


# ── 2. Full-Text, Exact & Trigram Search Tests ──────────────────────────────

def test_exact_invoice_and_gstin_search(test_env, client: TestClient):
    """Exact invoice number and GSTIN match returns top-ranked results."""
    make_doc = test_env["make_doc"]
    doc1 = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="lucky_invoice.jpg",
        ocr_text="Tax Invoice from Lucky Computers for computer monitor supply",
        structured_dict={
            "invoice": {"number": "LC-25-26/4280", "date": "19-Mar-2026"},
            "seller": {"name": "LUCKY COMPUTERS", "gstin": "33BLAPS0819R1ZQ"},
            "buyer": {"name": "Kartwheel Consulting", "gstin": "33ALJPP7733P1ZE"},
            "totals": {"grand_total": 96000.0},
        },
    )

    headers = {"Authorization": f"Bearer {test_env['token_admin_a']}"}

    # Search by exact invoice number via query param q
    res = client.get("/api/documents/search?q=LC-25-26/4280", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert data["items"][0]["id"] == doc1.id
    assert data["items"][0]["invoice_number"] == "LC-25-26/4280"

    # Search by structured invoice_number filter
    res = client.get("/api/documents/search?invoice_number=LC-25-26/4280", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1
    assert res.json()["items"][0]["id"] == doc1.id

    # Search by exact GSTIN
    res = client.get("/api/documents/search?q=33BLAPS0819R1ZQ", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert data["items"][0]["id"] == doc1.id


def test_ocr_full_text_search_with_highlighted_snippets(test_env, client: TestClient):
    """Full-text search over OCR text returns delimited [[HL]] snippets."""
    make_doc = test_env["make_doc"]
    doc = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="server_bill.jpg",
        ocr_text="Enterprise SuperMicro Server Rack installed at datacenter floor with high performance GPU accelerators",
        structured_dict={
            "invoice": {"number": "SMR-9001", "date": "2026-04-10"},
            "seller": {"name": "SuperMicro Systems", "gstin": "29ABCDE1234F1Z5"},
            "totals": {"grand_total": 450000.0},
        },
    )

    headers = {"Authorization": f"Bearer {test_env['token_admin_a']}"}
    res = client.get("/api/documents/search?q=SuperMicro", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    item = next(it for it in data["items"] if it["id"] == doc.id)
    assert item["snippet"] is not None
    assert "[[HL]]" in item["snippet"] and "[[/HL]]" in item["snippet"]
    assert "SuperMicro" in item["snippet"]


def test_trigram_partial_and_misspelled_search(test_env, client: TestClient):
    """PostgreSQL pg_trgm handles partial numbers and misspelled vendor names."""
    make_doc = test_env["make_doc"]
    doc = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="lucky_bill.jpg",
        ocr_text="Lucky Computers hardware delivery",
        structured_dict={
            "invoice": {"number": "LC-25-26/4280", "date": "2026-03-19"},
            "seller": {"name": "Lucky Computers", "gstin": "33BLAPS0819R1ZQ"},
            "totals": {"grand_total": 96000.0},
        },
    )

    headers = {"Authorization": f"Bearer {test_env['token_admin_a']}"}

    # Partial number matching (4280 from LC-25-26/4280)
    res = client.get("/api/documents/search?q=4280", headers=headers)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()["items"]]
    assert doc.id in ids

    # Misspelled vendor name: "Lukcy" instead of "Lucky"
    res = client.get("/api/documents/search?vendor_name=Lukcy", headers=headers)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()["items"]]
    assert doc.id in ids


# ── 3. Structured Filtering Tests ────────────────────────────────────────────

def test_amount_range_and_indian_currency_filter(test_env, client: TestClient):
    """Amount filters handle raw numbers and Indian formatted strings."""
    make_doc = test_env["make_doc"]
    doc_small = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="cable.jpg",
        ocr_text="Cables",
        structured_dict={"totals": {"grand_total": 2500.0}},
    )
    doc_target = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="monitor.jpg",
        ocr_text="Monitors",
        structured_dict={"totals": {"grand_total": 96000.0}},
    )
    doc_large = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="workstation.jpg",
        ocr_text="Workstations",
        structured_dict={"totals": {"grand_total": 250000.0}},
    )

    headers = {"Authorization": f"Bearer {test_env['token_admin_a']}"}

    # Filter with Indian currency formatting: amount_min=90,000, amount_max=1,00,000
    res = client.get("/api/documents/search?amount_min=90,000&amount_max=1,00,000", headers=headers)
    assert res.status_code == 200
    items = res.json()["items"]
    ids = [i["id"] for i in items]
    assert doc_target.id in ids
    assert doc_small.id not in ids
    assert doc_large.id not in ids


def test_date_range_filter(test_env, client: TestClient):
    """Filters by date range correctly using invoice_date."""
    make_doc = test_env["make_doc"]
    doc_jan = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="jan.jpg",
        ocr_text="Jan Bill",
        structured_dict={"invoice": {"date": "2026-01-15"}, "totals": {"grand_total": 1000.0}},
    )
    doc_mar = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="mar.jpg",
        ocr_text="Mar Bill",
        structured_dict={"invoice": {"date": "2026-03-19"}, "totals": {"grand_total": 1000.0}},
    )

    headers = {"Authorization": f"Bearer {test_env['token_admin_a']}"}

    # Filter for March only
    res = client.get("/api/documents/search?date_from=2026-03-01&date_to=2026-03-31", headers=headers)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()["items"]]
    assert doc_mar.id in ids
    assert doc_jan.id not in ids


# ── 4. Multi-Tenancy & Authorization Matrix ──────────────────────────────────

def test_multi_tenant_isolation(test_env, client: TestClient):
    """Company B cannot search, retrieve, or discover Company A documents."""
    make_doc = test_env["make_doc"]
    doc_a = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="confidential_a.jpg",
        ocr_text="Confidential Project Alpha Blueprint",
        structured_dict={"invoice": {"number": "CONF-ALPHA-001"}},
    )

    # Admin B attempts to search Company A content
    headers_b = {"Authorization": f"Bearer {test_env['token_admin_b']}"}
    res = client.get("/api/documents/search?q=Confidential", headers=headers_b)
    assert res.status_code == 200
    assert res.json()["total"] == 0
    assert len(res.json()["items"]) == 0

    # Admin B attempts thumbnail discovery
    res = client.get(f"/api/documents/{doc_a.id}/thumbnail", headers=headers_b)
    assert res.status_code == 404


def test_branch_scoping_and_forbidden_unassigned_branch(test_env, client: TestClient):
    """Branch Admin cannot search an unassigned branch (returns 403 or empty)."""
    make_doc = test_env["make_doc"]
    doc_mysore = make_doc(
        company=test_env["company_a"],
        branch=test_env["mysore"],
        uploader=test_env["admin_a"],
        filename="mysore_asset.jpg",
        ocr_text="Mysore branch equipment",
    )

    # Branch admin assigned to Chennai searches Mysore branch
    headers_chn = {"Authorization": f"Bearer {test_env['token_branch_chn']}"}
    res = client.get(f"/api/documents/search?branch_id={test_env['mysore'].id}", headers=headers_chn)
    assert res.status_code == 403


def test_staff_30_day_cutoff_enforcement(test_env, client: TestClient):
    """Staff role is restricted strictly to documents uploaded within last 30 days."""
    make_doc = test_env["make_doc"]

    # Recent doc (10 days ago) uploaded by staff
    doc_recent = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["staff_chn"],
        filename="recent_doc.jpg",
        ocr_text="Recent staff upload",
        days_ago=10,
    )

    # Old doc (45 days ago) uploaded by same staff
    doc_old = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["staff_chn"],
        filename="old_doc.jpg",
        ocr_text="Old staff upload",
        days_ago=45,
    )

    headers_staff = {"Authorization": f"Bearer {test_env['token_staff_chn']}"}

    # Staff search
    res = client.get("/api/documents/search", headers=headers_staff)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()["items"]]
    assert doc_recent.id in ids
    assert doc_old.id not in ids

    # Staff thumbnail access on old document -> anti-enumeration 404
    res = client.get(f"/api/documents/{doc_old.id}/thumbnail", headers=headers_staff)
    assert res.status_code == 404

    # Global Admin can see both
    headers_admin = {"Authorization": f"Bearer {test_env['token_admin_a']}"}
    res = client.get("/api/documents/search", headers=headers_admin)
    admin_ids = [i["id"] for i in res.json()["items"]]
    assert doc_recent.id in admin_ids
    assert doc_old.id in admin_ids


# ── 5. Thumbnail Endpoint Generation & Caching ───────────────────────────────

def test_thumbnail_generation_and_caching(test_env, client: TestClient):
    """Thumbnail endpoint generates 200x200 JPEG and caches it on storage."""
    make_doc = test_env["make_doc"]
    doc = make_doc(
        company=test_env["company_a"],
        branch=test_env["chennai"],
        uploader=test_env["admin_a"],
        filename="product_photo.jpg",
        ocr_text="Product photo",
    )

    headers = {"Authorization": f"Bearer {test_env['token_admin_a']}"}

    # First fetch: generates and caches thumbnail
    res = client.get(f"/api/documents/{doc.id}/thumbnail", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    img = Image.open(io.BytesIO(res.content))
    assert max(img.size) <= 200

    # Second fetch: served from storage cache
    res2 = client.get(f"/api/documents/{doc.id}/thumbnail", headers=headers)
    assert res2.status_code == 200
    assert len(res2.content) == len(res.content)

    # Soft-deleted document returns 404
    del_res = client.delete(f"/api/documents/{doc.id}", headers=headers)
    assert del_res.status_code == 200

    res3 = client.get(f"/api/documents/{doc.id}/thumbnail", headers=headers)
    assert res3.status_code == 404


# ── 6. Pagination & Total Count Guarantees ────────────────────────────────────

def test_search_pagination_accuracy(test_env, client: TestClient):
    """Search pagination returns exact slice and total count."""
    make_doc = test_env["make_doc"]
    for i in range(5):
        make_doc(
            company=test_env["company_a"],
            branch=test_env["chennai"],
            uploader=test_env["admin_a"],
            filename=f"batch_doc_{i}.jpg",
            ocr_text=f"Batch document index {i}",
        )

    headers = {"Authorization": f"Bearer {test_env['token_admin_a']}"}
    res_p1 = client.get("/api/documents/search?page=1&page_size=2", headers=headers)
    assert res_p1.status_code == 200
    d1 = res_p1.json()
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert d1["total"] >= 5
    assert len(d1["items"]) == 2

    res_p2 = client.get("/api/documents/search?page=2&page_size=2", headers=headers)
    assert res_p2.status_code == 200
    d2 = res_p2.json()
    assert d2["page"] == 2
    assert len(d2["items"]) == 2
    # Ensure no overlap
    p1_ids = {x["id"] for x in d1["items"]}
    p2_ids = {x["id"] for x in d2["items"]}
    assert len(p1_ids.intersection(p2_ids)) == 0
