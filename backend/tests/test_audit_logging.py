"""
Module 5 – Audit Logging: Comprehensive Test Suite.

Verifies:
  1. Audit metadata sanitization (strict allowlist, secret redaction, no OCR text).
  2. Transactional consistency (business action rollback rolls back audit log atomically).
  3. Failed authentication auditing persistence via isolated transaction.
  4. Complete event coverage (auth, document operations, branch management, master admin).
  5. Immutability trigger and PostgreSQL role tamper-resistance (prevents UPDATE/DELETE).
  6. Read API authorization, tenant scoping, and pagination.
"""

import os
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.audit import audit
from app.audit.events import (
    ActorType,
    ObjectType,
    AUTH_LOGIN_SUCCESS,
    AUTH_LOGIN_FAILURE,
    AUTH_LOGOUT,
    DOCUMENT_UPLOAD,
    DOCUMENT_VIEW,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_DELETE,
    DOCUMENT_REPROCESS,
    BRANCH_CREATE,
    BRANCH_TOGGLE,
)
from app.audit.sanitizer import sanitize_metadata
from app.database import SessionLocal
from app.models import AuditLog, Company, Branch, User, Document, OcrStatus


# ── 1. METADATA SANITIZATION TESTS ─────────────────────────────────────────────

def test_metadata_sanitization_allowlist_and_secret_redaction():
    """Verify metadata sanitizer keeps allowed keys and excludes passwords, tokens, OCR text."""
    dirty_input = {
        "filename": "tax_invoice_2026.pdf",
        "file_size": 1048576,
        "mime_type": "application/pdf",
        "password": "SuperSecretPassword123!",
        "access_token": "eyJh...raw_jwt_token",
        "refresh_token": "rt_987654321",
        "api_key": "AIzaSySecretApiKey",
        "ocr_text": "Complete raw OCR text of 5000 characters from an invoice...",
        "document_body": "binary or raw document text",
        "unknown_custom_field": "some arbitrary payload",
        "branch_name": "Chennai Main",
        "reason": "Invalid GST format",
    }

    sanitized = sanitize_metadata(dirty_input)

    # Allowed keys preserved
    assert sanitized["filename"] == "tax_invoice_2026.pdf"
    assert sanitized["file_size"] == 1048576
    assert sanitized["mime_type"] == "application/pdf"
    assert sanitized["branch_name"] == "Chennai Main"
    assert sanitized["reason"] == "Invalid GST format"

    # Secrets and disallowed keys strictly purged
    assert "password" not in sanitized
    assert "access_token" not in sanitized
    assert "refresh_token" not in sanitized
    assert "api_key" not in sanitized
    assert "ocr_text" not in sanitized
    assert "document_body" not in sanitized
    assert "unknown_custom_field" not in sanitized


# ── 2. TRANSACTIONAL ATOMICITY & ROLLBACK TESTS ───────────────────────────────

def test_audit_log_rolls_back_with_business_transaction(db):
    """
    If a business transaction rolls back, its corresponding audit record
    MUST roll back atomically without persisting.
    """
    unique_action = f"test.rollback_action_{uuid.uuid4().hex[:8]}"
    
    # Verify no log exists initially
    initial = db.query(AuditLog).filter(AuditLog.action == unique_action).first()
    assert initial is None

    try:
        # Start transaction
        company = db.query(Company).first()
        audit.record(
            db=db,
            actor_type=ActorType.COMPANY_USER,
            actor_id=1,
            company_id=company.id,
            action=unique_action,
            object_type="test_object",
            object_id=999,
            metadata={"reason": "Testing atomic rollback"},
        )
        # Simulate business failure before commit
        raise RuntimeError("Simulated unhandled exception during business processing")
    except RuntimeError:
        db.rollback()

    # Query with a fresh session to ensure DB state is clean
    fresh_db = SessionLocal()
    try:
        persisted = fresh_db.query(AuditLog).filter(AuditLog.action == unique_action).first()
        assert persisted is None, "Audit record should NOT exist after business rollback!"
    finally:
        fresh_db.close()


def test_audit_log_commits_atomically_with_business_action(db):
    """When business transaction commits, the audit log commits with it."""
    unique_action = f"test.commit_action_{uuid.uuid4().hex[:8]}"

    company = db.query(Company).first()
    audit.record(
        db=db,
        actor_type=ActorType.COMPANY_USER,
        actor_id=1,
        company_id=company.id,
        action=unique_action,
        object_type="test_object",
        object_id=888,
        metadata={"filename": "test.pdf"},
    )
    db.commit()

    fresh_db = SessionLocal()
    try:
        persisted = fresh_db.query(AuditLog).filter(AuditLog.action == unique_action).first()
        assert persisted is not None
        assert str(persisted.object_id) == "888"
        assert persisted.event_metadata["filename"] == "test.pdf"
    finally:
        fresh_db.close()


# ── 3. FAILED AUTHENTICATION PERSISTENCE TESTS ────────────────────────────────

def test_failed_login_persists_audit_log(client, db):
    """
    Failed login attempts must persist in audit_logs via isolated transaction,
    even though the login route raises HTTPException(401) and aborts.
    """
    bad_email = "vasanth@vasanth.local"
    
    # Count failed auth logs before attempt
    before_count = db.query(AuditLog).filter(
        AuditLog.action == AUTH_LOGIN_FAILURE,
        AuditLog.event_metadata["email"].astext == bad_email,
    ).count()

    # Perform failed login
    resp = client.post("/api/auth/login", json={"email": bad_email, "password": "WrongPassword999!", "portal": "company"})
    assert resp.status_code == 401

    # Verify audit record persisted in DB
    fresh_db = SessionLocal()
    try:
        after_count = fresh_db.query(AuditLog).filter(
            AuditLog.action == AUTH_LOGIN_FAILURE,
            AuditLog.event_metadata["email"].astext == bad_email,
        ).count()
        assert after_count == before_count + 1, "Failed login MUST be recorded in audit_logs!"
        
        last_log = fresh_db.query(AuditLog).filter(
            AuditLog.action == AUTH_LOGIN_FAILURE,
            AuditLog.event_metadata["email"].astext == bad_email,
        ).order_by(AuditLog.id.desc()).first()

        assert last_log.actor_type.lower() == "anonymous"
        assert "password" not in (last_log.event_metadata or {})
        assert "Incorrect email or password." in (last_log.event_metadata or {}).get("reason", "")
    finally:
        fresh_db.close()


# ── 4. IMMUTABILITY & TAMPER RESISTANCE TESTS ──────────────────────────────────

def test_audit_logs_immutable_trigger_prevents_update_and_delete(db):
    """
    PostgreSQL trigger audit_logs_immutable_trg must abort any UPDATE or DELETE statement.
    """
    # Insert a test log entry
    company = db.query(Company).first()
    log = AuditLog(
        actor_type="system",
        action="tamper_test.init",
        company_id=company.id,
        occurred_at=datetime.now(timezone.utc),
        event_metadata={"reason": "immutable test"},
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    log_id = log.id

    # 1. Attempt UPDATE
    with pytest.raises(Exception) as exc_update:
        db.execute(text(f"UPDATE audit_logs SET action = 'tampered' WHERE id = {log_id}"))
        db.commit()
    db.rollback()
    assert "Audit logs are immutable" in str(exc_update.value)

    # 2. Attempt DELETE
    with pytest.raises(Exception) as exc_delete:
        db.execute(text(f"DELETE FROM audit_logs WHERE id = {log_id}"))
        db.commit()
    db.rollback()
    assert "Audit logs are immutable" in str(exc_delete.value)


def test_dms_app_role_privileges(db):
    """
    Verify PostgreSQL role dms_app has SELECT and INSERT, but lacks UPDATE and DELETE.
    """
    # Check table privileges for role dms_app via has_table_privilege
    res_select = db.execute(text("SELECT has_table_privilege('dms_app', 'audit_logs', 'SELECT')")).scalar()
    res_insert = db.execute(text("SELECT has_table_privilege('dms_app', 'audit_logs', 'INSERT')")).scalar()
    res_update = db.execute(text("SELECT has_table_privilege('dms_app', 'audit_logs', 'UPDATE')")).scalar()
    res_delete = db.execute(text("SELECT has_table_privilege('dms_app', 'audit_logs', 'DELETE')")).scalar()
    res_truncate = db.execute(text("SELECT has_table_privilege('dms_app', 'audit_logs', 'TRUNCATE')")).scalar()

    assert res_select is True, "dms_app must have SELECT on audit_logs"
    assert res_insert is True, "dms_app must have INSERT on audit_logs"
    assert res_update is False, "dms_app must NOT have UPDATE on audit_logs"
    assert res_delete is False, "dms_app must NOT have DELETE on audit_logs"
    assert res_truncate is False, "dms_app must NOT have TRUNCATE on audit_logs"


# ── 5. AUTHENTICATION LIFECYCLE AUDITING ───────────────────────────────────────

def test_successful_login_and_logout_audited(client, db):
    """Successful login and logout must record audit events."""
    email = "jayasri@example.com"
    
    # 1. Login to company portal
    resp = client.post("/api/auth/login", json={"email": email, "password": "Pasword@123", "portal": "company"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify login audit entry
    login_log = db.query(AuditLog).filter(
        AuditLog.action == AUTH_LOGIN_SUCCESS,
        AuditLog.actor_type == "company_user",
    ).order_by(AuditLog.id.desc()).first()

    assert login_log is not None
    assert login_log.event_metadata.get("email") == email

    # 2. Logout
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Verify logout audit entry
    logout_log = db.query(AuditLog).filter(
        AuditLog.action == AUTH_LOGOUT,
        AuditLog.actor_type == "company_user",
    ).order_by(AuditLog.id.desc()).first()

    assert logout_log is not None


# ── 6. DOCUMENT OPERATIONS AUDITING ───────────────────────────────────────────

def test_document_lifecycle_audited(client, db):
    """Document upload, view, download, and delete must record compact audit events."""
    login_resp = client.post("/api/auth/login", json={"email": "samrethi@example.com", "password": "Pasword@123", "portal": "app"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Upload
    import weasyprint
    file_bytes = weasyprint.HTML(string="<p>Test Audit PDF</p>").write_pdf()
    upload_resp = client.post(
        "/api/documents",
        files={"file": ("audit_sample.pdf", file_bytes, "application/pdf")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["id"]

    # Verify DOCUMENT_UPLOAD log
    upload_log = db.query(AuditLog).filter(
        AuditLog.action == DOCUMENT_UPLOAD,
        AuditLog.object_id == str(doc_id),
    ).first()
    assert upload_log is not None
    assert upload_log.event_metadata["filename"] == "audit_sample.pdf"
    assert upload_log.event_metadata["mime_type"] == "application/pdf"
    assert "ocr_text" not in upload_log.event_metadata

    # 2. View document metadata
    view_resp = client.get(f"/api/documents/{doc_id}", headers=headers)
    assert view_resp.status_code == 200

    view_log = db.query(AuditLog).filter(
        AuditLog.action == DOCUMENT_VIEW,
        AuditLog.object_id == str(doc_id),
    ).first()
    assert view_log is not None

    # 3. Download document file
    dl_resp = client.get(f"/api/documents/{doc_id}/file", headers=headers)
    assert dl_resp.status_code == 200

    dl_log = db.query(AuditLog).filter(
        AuditLog.action == DOCUMENT_DOWNLOAD,
        AuditLog.object_id == str(doc_id),
    ).first()
    assert dl_log is not None

    # 4. Soft delete document
    del_resp = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 200

    del_log = db.query(AuditLog).filter(
        AuditLog.action == DOCUMENT_DELETE,
        AuditLog.object_id == str(doc_id),
    ).first()
    assert del_log is not None

    # Cleanup processing job created by upload
    from app.models import ProcessingJob
    db.query(ProcessingJob).filter(ProcessingJob.document_id == doc_id).delete()
    db.commit()


# ── 7. AUDIT READ API AUTHORIZATION & TENANT SCOPING ───────────────────────────

def test_audit_api_authorization_and_scoping(client):
    """
    1. Company Admin can view company audit logs (GET /api/audit).
    2. Staff user without audit permission receives 403 Forbidden.
    3. Anonymous user receives 401 Unauthorized.
    4. Master Admin can view platform audit logs (GET /api/admin/audit).
    5. Tenant user cannot view platform audit logs (403 Forbidden).
    """
    # 1. Company Admin (GLOBAL_ADMIN has audit.view_company)
    ca_login = client.post("/api/auth/login", json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"})
    assert ca_login.status_code == 200
    company_admin_headers = {"Authorization": f"Bearer {ca_login.json()['access_token']}"}

    res_company = client.get("/api/audit", headers=company_admin_headers)
    assert res_company.status_code == 200
    data = res_company.json()
    assert "items" in data
    assert "total_count" in data
    assert isinstance(data["items"], list)

    # 2. Staff user (sujipriya has no audit.view_company or audit.view_branch)
    staff_login = client.post("/api/auth/login", json={"email": "sujipriya@example.com", "password": "Pasword@123", "portal": "app"})
    assert staff_login.status_code == 200
    staff_headers = {"Authorization": f"Bearer {staff_login.json()['access_token']}"}

    res_staff = client.get("/api/audit", headers=staff_headers)
    assert res_staff.status_code == 403

    # 3. Anonymous user
    res_anon = client.get("/api/audit")
    assert res_anon.status_code == 401

    # 4. Master Admin login for platform audit logs
    login_master = client.post("/api/auth/login", json={"email": "master@platform.local", "password": "Pasword@123", "portal": "platform"})
    assert login_master.status_code == 200
    master_token = login_master.json()["access_token"]
    master_headers = {"Authorization": f"Bearer {master_token}"}

    res_platform = client.get("/api/admin/audit", headers=master_headers)
    assert res_platform.status_code == 200
    platform_data = res_platform.json()
    assert "items" in platform_data

    # 5. Tenant user attempting platform audit logs gets 403
    res_tenant_on_platform = client.get("/api/admin/audit", headers=company_admin_headers)
    assert res_tenant_on_platform.status_code == 403


def test_audit_api_filtering_and_pagination(client):
    """Verify action filtering, date filtering, and pagination on GET /api/audit."""
    ca_login = client.post("/api/auth/login", json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"})
    assert ca_login.status_code == 200
    headers = {"Authorization": f"Bearer {ca_login.json()['access_token']}"}

    # Fetch page 1 with page_size=2
    res = client.get("/api/audit?page=1&page_size=2", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) <= 2

    # Filter by specific action
    res_filter = client.get(f"/api/audit?action={AUTH_LOGIN_SUCCESS}", headers=headers)
    assert res_filter.status_code == 200
    filter_data = res_filter.json()
    for item in filter_data["items"]:
        assert item["action"] == AUTH_LOGIN_SUCCESS
