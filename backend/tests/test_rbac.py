"""
Tests for role-based access control (RBAC) and tenant isolation.
"""

from datetime import datetime
import pytest
from app.models import Document, User, Tenant


@pytest.fixture(autouse=True)
def reset_document_deleted_state(db):
    """Ensure seeded documents are not marked deleted before each test run."""
    db.query(Document).filter(
        Document.original_filename.in_([
            "chennai_admin_doc.jpg",
            "mysore_admin_doc.jpg",
            "sujipriya_recent.jpg",
            "boomika_recent.jpg",
        ])
    ).update({Document.deleted_at: None, Document.deleted_by: None}, synchronize_session=False)
    db.commit()


def test_staff_cannot_delete_any_document(client, auth_headers, db):
    suji_headers = auth_headers("sujipriya@example.com")
    doc = db.query(Document).filter(Document.original_filename == "chennai_admin_doc.jpg").first()
    assert doc is not None

    resp = client.delete(f"/api/documents/{doc.id}", headers=suji_headers)
    assert resp.status_code == 403
    assert "staff cannot delete" in resp.json()["detail"].lower()


def test_tenant_admin_cannot_access_other_tenant_document(client, auth_headers, db):
    # Samrethi (Chennai Admin) tries to access Mysore doc
    samrethi_headers = auth_headers("samrethi@example.com")
    mysore_doc = db.query(Document).filter(Document.original_filename == "mysore_admin_doc.jpg").first()
    assert mysore_doc is not None

    # GET returns 404
    resp = client.get(f"/api/documents/{mysore_doc.id}", headers=samrethi_headers)
    assert resp.status_code == 404

    # DELETE returns 404
    resp = client.delete(f"/api/documents/{mysore_doc.id}", headers=samrethi_headers)
    assert resp.status_code == 404


def test_tenant_admin_can_delete_own_tenant_document(client, auth_headers, db):
    samrethi_headers = auth_headers("samrethi@example.com")
    chennai_doc = db.query(Document).filter(Document.original_filename == "chennai_admin_doc.jpg").first()
    assert chennai_doc is not None

    resp = client.delete(f"/api/documents/{chennai_doc.id}", headers=samrethi_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Now verify it is soft-deleted and cannot be fetched
    db.refresh(chennai_doc)
    assert chennai_doc.deleted_at is not None
    resp_after = client.get(f"/api/documents/{chennai_doc.id}", headers=samrethi_headers)
    assert resp_after.status_code == 404


def test_global_admin_can_access_all_tenants(client, auth_headers, db):
    jayasri_headers = auth_headers("jayasri@example.com")
    docs = client.get("/api/documents", headers=jayasri_headers).json()

    tenant_ids = {d["tenant_id"] for d in docs}
    # Should see documents from multiple tenants
    assert len(tenant_ids) >= 2


def test_staff_sees_only_own_recent_documents(client, auth_headers, db):
    suji_headers = auth_headers("sujipriya@example.com")
    docs = client.get("/api/documents", headers=suji_headers).json()

    suji_user = db.query(User).filter(User.email == "sujipriya@example.com").first()
    for d in docs:
        assert d["uploaded_by"] == suji_user.id
        # Should not see other users' documents
        assert d["original_filename"] != "chennai_admin_doc.jpg"
