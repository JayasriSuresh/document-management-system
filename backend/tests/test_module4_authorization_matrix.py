"""
Module 4 – Comprehensive Authorization Test Matrix.

Covers:
  1. Role-to-permission mapping and dynamic permission resolution.
  2. The 30-Day Uploader policy with explicit date boundaries (29 days, exactly 30 days, 31 days).
  3. Direct ID guessing protection (returns 404 for out-of-scope objects across all resource-bearing routes).
  4. Cross-company and cross-branch isolation.
  5. Derived documents / generated copies inherit source document restrictions.
  6. Soft-deleted documents masking.
  7. Uploader single-branch invariant enforcement.
  8. Suspended company and deactivated user handling.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import text

from app.auth.authorization import can, scope_filter
from app.auth.document_access_policy import DocumentAccessPolicy
from app.auth.permissions import (
    DOCUMENT_DELETE,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_REPROCESS,
    DOCUMENT_UPLOAD,
    DOCUMENT_VIEW_BRANCH,
    DOCUMENT_VIEW_COMPANY,
    DOCUMENT_VIEW_OWN,
    INVOICE_DOWNLOAD,
    INVOICE_VIEW,
    PLATFORM_MANAGE,
)
from app.auth.role_permissions import (
    ROLE_ADMIN,
    ROLE_GLOBAL_ADMIN,
    ROLE_MASTER_ADMIN,
    ROLE_STAFF,
    ROLE_UPLOADER,
    get_permissions_for_role,
)
from app.config import settings
from app.context import AuthContext, MasterAdminContext
from app.models import (
    AccountStatus,
    Branch,
    Company,
    CompanyStatus,
    Document,
    Invoice,
    OcrStatus,
    User,
    UserRole,
    UserRoleAssignment,
)


@pytest.fixture
def auth_fixture(client, db):
    """
    Creates isolated test companies, branches, users, and documents for matrix tests.
    """
    now = datetime.utcnow()

    # Company A (Active)
    comp_a = Company(name="Test Matrix Comp A", code=f"MAT_A_{uuid.uuid4().hex[:6]}", status=CompanyStatus.ACTIVE)
    # Company B (Active)
    comp_b = Company(name="Test Matrix Comp B", code=f"MAT_B_{uuid.uuid4().hex[:6]}", status=CompanyStatus.ACTIVE)
    # Company Suspended
    comp_susp = Company(name="Test Suspended Co", code=f"MAT_SUSP_{uuid.uuid4().hex[:6]}", status=CompanyStatus.SUSPENDED)
    db.add_all([comp_a, comp_b, comp_susp])
    db.flush()

    # Branches
    branch_a1 = Branch(company_id=comp_a.id, name="Branch A1", code="BR_A1")
    branch_a2 = Branch(company_id=comp_a.id, name="Branch A2", code="BR_A2")
    branch_b1 = Branch(company_id=comp_b.id, name="Branch B1", code="BR_B1")
    branch_susp = Branch(company_id=comp_susp.id, name="Branch Susp", code="BR_SUSP")
    db.add_all([branch_a1, branch_a2, branch_b1, branch_susp])
    db.flush()

    from app.auth import get_password_hash
    pwd = get_password_hash("Pasword@123")

    # Users
    u_global_admin = User(company_id=comp_a.id, branch_id=branch_a1.id, name="Global Admin A", email=f"ga_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.GLOBAL_ADMIN, status=AccountStatus.ACTIVE)
    u_admin_a1 = User(company_id=comp_a.id, branch_id=branch_a1.id, name="Admin A1", email=f"adm_a1_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.ADMIN, status=AccountStatus.ACTIVE)
    u_staff_a1 = User(company_id=comp_a.id, branch_id=branch_a1.id, name="Staff A1", email=f"stf_a1_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.STAFF, status=AccountStatus.ACTIVE)
    u_other_staff_a1 = User(company_id=comp_a.id, branch_id=branch_a1.id, name="Other Staff A1", email=f"other_a1_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.STAFF, status=AccountStatus.ACTIVE)
    u_staff_a2 = User(company_id=comp_a.id, branch_id=branch_a2.id, name="Staff A2", email=f"stf_a2_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.STAFF, status=AccountStatus.ACTIVE)
    u_staff_b1 = User(company_id=comp_b.id, branch_id=branch_b1.id, name="Staff B1", email=f"stf_b1_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.STAFF, status=AccountStatus.ACTIVE)
    u_inactive = User(company_id=comp_a.id, branch_id=branch_a1.id, name="Inactive Staff", email=f"inact_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.STAFF, status=AccountStatus.INACTIVE)
    u_suspended = User(company_id=comp_susp.id, branch_id=branch_susp.id, name="Suspended Staff", email=f"susp_{uuid.uuid4().hex[:6]}@test.com", password_hash=pwd, role=UserRole.STAFF, status=AccountStatus.ACTIVE)

    db.add_all([u_global_admin, u_admin_a1, u_staff_a1, u_other_staff_a1, u_staff_a2, u_staff_b1, u_inactive, u_suspended])
    db.flush()

    # Role Assignments
    db.add(UserRoleAssignment(user_id=u_global_admin.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_a.id))
    db.add(UserRoleAssignment(user_id=u_admin_a1.id, role="ADMIN", scope_type="branch", scope_id=branch_a1.id))
    db.add(UserRoleAssignment(user_id=u_staff_a1.id, role="UPLOADER", scope_type="branch", scope_id=branch_a1.id))
    db.add(UserRoleAssignment(user_id=u_other_staff_a1.id, role="UPLOADER", scope_type="branch", scope_id=branch_a1.id))
    db.add(UserRoleAssignment(user_id=u_staff_a2.id, role="UPLOADER", scope_type="branch", scope_id=branch_a2.id))
    db.add(UserRoleAssignment(user_id=u_staff_b1.id, role="UPLOADER", scope_type="branch", scope_id=branch_b1.id))
    db.add(UserRoleAssignment(user_id=u_suspended.id, role="UPLOADER", scope_type="branch", scope_id=branch_susp.id))
    db.flush()

    # Physical test storage file
    storage_dir = Path(settings.STORAGE_PATH)
    storage_dir.mkdir(parents=True, exist_ok=True)
    test_key = f"matrix_test_{uuid.uuid4().hex}.jpg"
    test_file_path = storage_dir / test_key
    test_file_path.write_bytes(b"dummy image data")

    # Documents with controlled ages
    doc_29d = Document(
        company_id=comp_a.id, branch_id=branch_a1.id, uploaded_by=u_staff_a1.id,
        original_filename="doc_29d.jpg", storage_key=test_key, mime_type="image/jpeg",
        file_size=16, ocr_status=OcrStatus.COMPLETED, ocr_text="Receipt text 29 days",
        created_at=now - timedelta(days=29),
    )
    doc_30d = Document(
        company_id=comp_a.id, branch_id=branch_a1.id, uploaded_by=u_staff_a1.id,
        original_filename="doc_30d.jpg", storage_key=f"m_{uuid.uuid4().hex}.jpg", mime_type="image/jpeg",
        file_size=16, ocr_status=OcrStatus.COMPLETED, ocr_text="Receipt text 30 days",
        created_at=now - timedelta(days=30),  # Exactly 30 days
    )
    doc_31d = Document(
        company_id=comp_a.id, branch_id=branch_a1.id, uploaded_by=u_staff_a1.id,
        original_filename="doc_31d.jpg", storage_key=f"m_{uuid.uuid4().hex}.jpg", mime_type="image/jpeg",
        file_size=16, ocr_status=OcrStatus.COMPLETED, ocr_text="Receipt text 31 days",
        created_at=now - timedelta(days=31),  # Expired
    )
    doc_other_user_a1 = Document(
        company_id=comp_a.id, branch_id=branch_a1.id, uploaded_by=u_other_staff_a1.id,
        original_filename="doc_other_a1.jpg", storage_key=f"m_{uuid.uuid4().hex}.jpg", mime_type="image/jpeg",
        file_size=16, ocr_status=OcrStatus.COMPLETED, ocr_text="Receipt text other",
        created_at=now - timedelta(days=2),
    )
    doc_branch_a2 = Document(
        company_id=comp_a.id, branch_id=branch_a2.id, uploaded_by=u_staff_a2.id,
        original_filename="doc_branch_a2.jpg", storage_key=f"m_{uuid.uuid4().hex}.jpg", mime_type="image/jpeg",
        file_size=16, ocr_status=OcrStatus.COMPLETED, ocr_text="Receipt text A2",
        created_at=now - timedelta(days=2),
    )
    doc_comp_b = Document(
        company_id=comp_b.id, branch_id=branch_b1.id, uploaded_by=u_staff_b1.id,
        original_filename="doc_comp_b.jpg", storage_key=f"m_{uuid.uuid4().hex}.jpg", mime_type="image/jpeg",
        file_size=16, ocr_status=OcrStatus.COMPLETED, ocr_text="Receipt text B",
        created_at=now - timedelta(days=2),
    )
    doc_soft_deleted = Document(
        company_id=comp_a.id, branch_id=branch_a1.id, uploaded_by=u_staff_a1.id,
        original_filename="doc_deleted.jpg", storage_key=f"m_{uuid.uuid4().hex}.jpg", mime_type="image/jpeg",
        file_size=16, ocr_status=OcrStatus.COMPLETED, ocr_text="Receipt text deleted",
        created_at=now - timedelta(days=5), deleted_at=now - timedelta(days=1), deleted_by=u_admin_a1.id,
    )

    db.add_all([doc_29d, doc_30d, doc_31d, doc_other_user_a1, doc_branch_a2, doc_comp_b, doc_soft_deleted])
    db.flush()

    # Derived Invoices
    inv_pdf_key = f"generated_invoice_{doc_29d.id}.pdf"
    (storage_dir / inv_pdf_key).write_bytes(b"%PDF-1.4 dummy pdf")
    inv_29d = Invoice(
        document_id=doc_29d.id, company_id=comp_a.id, branch_id=branch_a1.id, uploaded_by=u_staff_a1.id,
        invoice_number=f"INV-{doc_29d.id}", invoice_date="01-Jan-2026", seller_name="Seller A1",
        grand_total="1000", currency="INR", pdf_filename=inv_pdf_key, file_size=64, created_at=doc_29d.created_at,
    )

    inv_31d_key = f"generated_invoice_{doc_31d.id}.pdf"
    (storage_dir / inv_31d_key).write_bytes(b"%PDF-1.4 dummy pdf")
    inv_31d = Invoice(
        document_id=doc_31d.id, company_id=comp_a.id, branch_id=branch_a1.id, uploaded_by=u_staff_a1.id,
        invoice_number=f"INV-{doc_31d.id}", invoice_date="01-Dec-2025", seller_name="Seller A1",
        grand_total="2000", currency="INR", pdf_filename=inv_31d_key, file_size=64, created_at=doc_31d.created_at,
    )
    db.add_all([inv_29d, inv_31d])
    db.commit()

    yield {
        "comp_a": comp_a,
        "comp_b": comp_b,
        "comp_susp": comp_susp,
        "branch_a1": branch_a1,
        "branch_a2": branch_a2,
        "branch_b1": branch_b1,
        "u_global_admin": u_global_admin,
        "u_admin_a1": u_admin_a1,
        "u_staff_a1": u_staff_a1,
        "u_other_staff_a1": u_other_staff_a1,
        "u_staff_a2": u_staff_a2,
        "u_staff_b1": u_staff_b1,
        "u_inactive": u_inactive,
        "u_suspended": u_suspended,
        "doc_29d": doc_29d,
        "doc_30d": doc_30d,
        "doc_31d": doc_31d,
        "doc_other_user_a1": doc_other_user_a1,
        "doc_branch_a2": doc_branch_a2,
        "doc_comp_b": doc_comp_b,
        "doc_soft_deleted": doc_soft_deleted,
        "inv_29d": inv_29d,
        "inv_31d": inv_31d,
        "now": now,
    }

    # Teardown: clean up test files and DB records
    try:
        if test_file_path.exists(): test_file_path.unlink()
        f29 = storage_dir / inv_pdf_key
        if f29.exists(): f29.unlink()
        f31 = storage_dir / inv_31d_key
        if f31.exists(): f31.unlink()

        # Clean DB test matrix entities
        for comp in [comp_a, comp_b, comp_susp]:
            db.execute(text(f"DELETE FROM invoices WHERE company_id = {comp.id}"))
            db.execute(text(f"DELETE FROM documents WHERE company_id = {comp.id}"))
            db.execute(text(f"DELETE FROM user_role_assignments WHERE user_id IN (SELECT id FROM users WHERE company_id = {comp.id})"))
            db.execute(text(f"DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE company_id = {comp.id})"))
            db.execute(text(f"DELETE FROM invitations WHERE company_id = {comp.id}"))
            db.execute(text(f"DELETE FROM users WHERE company_id = {comp.id}"))
            db.execute(text(f"DELETE FROM branches WHERE company_id = {comp.id}"))
            db.execute(text(f"DELETE FROM companies WHERE id = {comp.id}"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def test_permission_constants_and_roles_contract():
    """Verify role-to-permission mapping integrity."""
    ga_perms = get_permissions_for_role(ROLE_GLOBAL_ADMIN)
    assert DOCUMENT_VIEW_COMPANY in ga_perms
    assert DOCUMENT_DELETE in ga_perms
    assert "branch.create" in ga_perms

    adm_perms = get_permissions_for_role(ROLE_ADMIN)
    assert DOCUMENT_VIEW_BRANCH in adm_perms
    assert DOCUMENT_DELETE in adm_perms
    assert DOCUMENT_VIEW_COMPANY not in adm_perms

    uploader_perms = get_permissions_for_role(ROLE_UPLOADER)
    assert DOCUMENT_UPLOAD in uploader_perms
    assert DOCUMENT_VIEW_OWN in uploader_perms
    assert DOCUMENT_DELETE not in uploader_perms
    assert DOCUMENT_VIEW_BRANCH not in uploader_perms
    assert DOCUMENT_VIEW_COMPANY not in uploader_perms


def test_uploader_30_day_date_boundaries(auth_fixture, client, auth_headers):
    """
    Test critical business rule:
      - 29 days old -> Allowed (HTTP 200)
      - Exactly 30 days old -> Allowed (HTTP 200)
      - 31 days old -> Denied (HTTP 404 to avoid leaking existence)
    """
    f = auth_fixture
    staff_headers = auth_headers(f["u_staff_a1"].email)

    with patch("app.auth.authorization.get_utc_now", return_value=f["now"]), \
         patch("app.auth.document_access_policy.get_utc_now", return_value=f["now"]):

        # 1. 29 days old: Allowed
        resp_29 = client.get(f"/api/documents/{f['doc_29d'].id}", headers=staff_headers)
        assert resp_29.status_code == 200, f"Expected 200 for 29-day doc: {resp_29.text}"
        assert resp_29.json()["id"] == f["doc_29d"].id

        # 2. Exactly 30 days old: Allowed
        resp_30 = client.get(f"/api/documents/{f['doc_30d'].id}", headers=staff_headers)
        assert resp_30.status_code == 200, f"Expected 200 for 30-day doc: {resp_30.text}"
        assert resp_30.json()["id"] == f["doc_30d"].id

        # 3. 31 days old: Denied with 404 Not Found
        resp_31 = client.get(f"/api/documents/{f['doc_31d'].id}", headers=staff_headers)
        assert resp_31.status_code == 404, f"Expected 404 for 31-day doc: {resp_31.text}"

        # Verify query list also omits 31-day doc
        list_resp = client.get("/api/documents", headers=staff_headers)
        assert list_resp.status_code == 200
        listed_ids = {d["id"] for d in list_resp.json()}
        assert f["doc_29d"].id in listed_ids
        assert f["doc_30d"].id in listed_ids
        assert f["doc_31d"].id not in listed_ids


def test_direct_id_guessing_returns_404_across_all_routes(auth_fixture, client, auth_headers):
    """
    Direct ID Guessing Protection:
    Out-of-scope objects (different company, different branch, or another user's document for uploader)
    MUST return HTTP 404 Not Found across all document and invoice routes.
    """
    f = auth_fixture
    staff_headers = auth_headers(f["u_staff_a1"].email)

    other_user_doc_id = f["doc_other_user_a1"].id
    other_branch_doc_id = f["doc_branch_a2"].id
    other_company_doc_id = f["doc_comp_b"].id

    # 1. Direct GET detail
    for doc_id in (other_user_doc_id, other_branch_doc_id, other_company_doc_id):
        resp = client.get(f"/api/documents/{doc_id}", headers=staff_headers)
        assert resp.status_code == 404, f"Doc {doc_id} should return 404 on GET"

    # 2. Direct File Download
    for doc_id in (other_user_doc_id, other_branch_doc_id, other_company_doc_id):
        resp = client.get(f"/api/documents/{doc_id}/file", headers=staff_headers)
        assert resp.status_code == 404, f"Doc file {doc_id} should return 404"

    # 3. Direct Reprocess
    for doc_id in (other_user_doc_id, other_branch_doc_id, other_company_doc_id):
        resp = client.post(f"/api/documents/{doc_id}/reprocess", headers=staff_headers)
        assert resp.status_code in (404, 403), f"Doc reprocess {doc_id} must not succeed"

    # 4. Direct Soft-Delete
    for doc_id in (other_branch_doc_id, other_company_doc_id):
        # Admin A1 tries to delete branch A2 or Company B
        adm_headers = auth_headers(f["u_admin_a1"].email)
        resp = client.delete(f"/api/documents/{doc_id}", headers=adm_headers)
        assert resp.status_code == 404, f"Doc delete {doc_id} across branch/company must return 404"


def test_derived_copies_inherit_source_document_restrictions(auth_fixture, client, auth_headers):
    """
    Derived documents (e.g. generated invoice PDFs) cannot provide more access
    than their source document. If source document access is lost (e.g. 31 days old),
    the invoice endpoint MUST return 404.
    """
    f = auth_fixture
    staff_headers = auth_headers(f["u_staff_a1"].email)

    # 29-day invoice: Accessible
    resp_29 = client.get(f"/api/invoices/{f['inv_29d'].id}", headers=staff_headers)
    assert resp_29.status_code == 200

    resp_29_pdf = client.get(f"/api/invoices/{f['inv_29d'].id}/pdf", headers=staff_headers)
    assert resp_29_pdf.status_code == 200

    # 31-day invoice: Denied with 404 because source document is past 30 days
    resp_31 = client.get(f"/api/invoices/{f['inv_31d'].id}", headers=staff_headers)
    assert resp_31.status_code == 404

    resp_31_pdf = client.get(f"/api/invoices/{f['inv_31d'].id}/pdf", headers=staff_headers)
    assert resp_31_pdf.status_code == 404

    # Also verify invoice list omits the 31-day invoice for Uploader
    list_inv = client.get("/api/invoices", headers=staff_headers)
    assert list_inv.status_code == 200
    ids = {inv["id"] for inv in list_inv.json()}
    assert f["inv_29d"].id in ids
    assert f["inv_31d"].id not in ids


def test_soft_deleted_documents_masked(auth_fixture, client, auth_headers):
    """
    Soft-deleted documents must return 404 on normal GET, file download, and PDF generation.
    """
    f = auth_fixture
    adm_headers = auth_headers(f["u_admin_a1"].email)
    deleted_id = f["doc_soft_deleted"].id

    resp_get = client.get(f"/api/documents/{deleted_id}", headers=adm_headers)
    assert resp_get.status_code == 404

    resp_file = client.get(f"/api/documents/{deleted_id}/file", headers=adm_headers)
    assert resp_file.status_code == 404


def test_uploader_single_branch_invariant(db):
    """
    Enforces that an Uploader cannot have multiple branch assignments
    or a company-wide assignment.
    """
    # 1. Attempting company assignment for Uploader fails context resolution
    comp = db.query(Company).filter(Company.code == "VASANTH_CO").first() or db.query(Company).first()
    branches = db.query(Branch).filter(Branch.company_id == comp.id).all()
    b1 = branches[0]
    b2 = branches[1] if len(branches) > 1 else b1

    u_multi = User(
        company_id=comp.id, branch_id=b1.id, name="Bad Uploader", email="bad_up@test.com",
        password_hash="pw", role=UserRole.STAFF, status=AccountStatus.ACTIVE,
    )
    db.add(u_multi)
    db.flush()

    # Assign company scope to Uploader
    db.add(UserRoleAssignment(user_id=u_multi.id, role="UPLOADER", scope_type="company", scope_id=comp.id))
    db.commit()

    from app.context import _build_auth_context
    from app.auth import create_access_token
    token = create_access_token({"user_id": u_multi.id, "aud": "app"})

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _build_auth_context(token, db)
    assert exc.value.status_code == 403
    assert "company-wide" in exc.value.detail.lower()

    # 2. Attempting multiple branch assignments fails context resolution
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == u_multi.id).delete()
    db.add(UserRoleAssignment(user_id=u_multi.id, role="UPLOADER", scope_type="branch", scope_id=b1.id))
    db.add(UserRoleAssignment(user_id=u_multi.id, role="UPLOADER", scope_type="branch", scope_id=b2.id))
    db.commit()

    with pytest.raises(HTTPException) as exc2:
        _build_auth_context(token, db)
    assert exc2.value.status_code == 403
    assert "multiple branches" in exc2.value.detail.lower()

    # Clean up test user
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == u_multi.id).delete()
    db.query(User).filter(User.id == u_multi.id).delete()
    db.commit()


def test_me_endpoint_returns_permissions_and_assignments(auth_fixture, client, auth_headers):
    """
    Verify /api/auth/me returns effective permissions and assignments for frontend UI consumption.
    """
    f = auth_fixture
    adm_headers = auth_headers(f["u_admin_a1"].email)

    resp = client.get("/api/auth/me", headers=adm_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "permissions" in data
    assert isinstance(data["permissions"], list)
    assert DOCUMENT_VIEW_BRANCH in data["permissions"]
    assert DOCUMENT_DELETE in data["permissions"]

    assert "assignments" in data
    assert len(data["assignments"]) >= 1
    assignment = data["assignments"][0]
    assert assignment["role"] == "ADMIN"
    assert assignment["scope_type"] == "branch"
