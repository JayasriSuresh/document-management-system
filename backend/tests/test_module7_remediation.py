"""
Module 7 Remediation and Security Hardening Verification Tests.

Verifies:
  1. GLOBAL_ADMIN cannot bypass company suspension (returns 403 Forbidden).
  2. Quota enforcement:
     - max_branches prevents branch creation beyond limit (400 Bad Request).
     - max_users prevents user invitation beyond limit (400 Bad Request).
     - storage_limit_bytes prevents document uploads beyond limit (413 Payload Too Large).
     - monthly_ai_budget_cents halts OCR reprocessing when exceeded (402 Payment Required).
  3. Platform Dashboard endpoint returns aggregated metrics and recent activity.
  4. Company Details and Quotas API (GET and PUT /api/admin/companies/{id}).
  5. System Settings API (GET and PUT /api/admin/settings).
  6. File upload magic bytes validation (blocks spoofed documents).
  7. Onboarding approval provisions mandatory MFA and creates a 72-hour invitation.
"""

import io
import uuid
from datetime import datetime, timedelta
import pytest
from app.models import (
    Company, Branch, User, UserRole, CompanyStatus, AccountStatus, Document,
    AIUsageLedger, CompanyOnboarding, OnboardingStatus, Invitation, AuditLog
)
from app.audit.events import MASTER_ADMIN_COMPANY_UPDATE


def get_master_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "master@platform.local", "password": "Pasword@123", "portal": "platform"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def get_company_admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ── 1. Company Suspension Blocks GLOBAL_ADMIN ────────────────────────────────

def test_company_suspension_blocks_global_admin(client, db):
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    assert vasanth is not None
    token = get_company_admin_token(client)

    # 1. Active company allows access
    resp = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    try:
        # 2. Suspend company
        vasanth.status = CompanyStatus.SUSPENDED
        db.commit()

        # 3. GLOBAL_ADMIN should now receive 403 Forbidden
        resp_suspended = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
        assert resp_suspended.status_code == 403
        assert "suspended" in resp_suspended.json()["detail"].lower()
    finally:
        vasanth.status = CompanyStatus.ACTIVE
        db.commit()


# ── 2. Quota Enforcement ────────────────────────────────────────────────────

def test_branch_quota_enforcement(client, db):
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    original_max = vasanth.max_branches
    token = get_company_admin_token(client)

    try:
        # Set max_branches to current count (2)
        current_count = db.query(Branch).filter(Branch.company_id == vasanth.id).count()
        vasanth.max_branches = current_count
        db.commit()

        # Attempt to create an additional branch
        payload = {
            "branch_name": "Coimbatore Branch",
            "branch_code": "CBE",
            "branch_type": "Branch",
            "branch_contact_number": "9876543210",
            "address_line1": "123 Main Road",
            "city": "Coimbatore",
            "district": "Coimbatore",
            "state": "Tamil Nadu",
            "pincode": "641001",
            "admin_name": "Coimbatore Admin",
            "admin_email": "cbe.admin@example.com",
            "admin_mobile": "9876543210",
        }
        resp = client.post(
            "/api/company/branches",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "limit reached" in resp.json()["detail"].lower()
    finally:
        vasanth.max_branches = original_max
        db.commit()


def test_user_quota_enforcement(client, db):
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    original_max = vasanth.max_users
    chennai = db.query(Branch).filter(Branch.company_id == vasanth.id, Branch.code == "CHENNAI").first()
    token = get_company_admin_token(client)

    try:
        # Set max_users to current active count
        current_users = db.query(User).filter(User.company_id == vasanth.id, User.status == AccountStatus.ACTIVE).count()
        vasanth.max_users = current_users
        db.commit()

        # Attempt to invite a new user
        resp = client.post(
            "/api/auth/invite",
            json={
                "email": f"quota_test_{uuid.uuid4().hex[:4]}@example.com",
                "invited_role": "STAFF",
                "branch_id": chennai.id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "limit reached" in resp.json()["detail"].lower()
    finally:
        vasanth.max_users = original_max
        db.commit()


def test_storage_quota_enforcement(client, db):
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    original_limit = vasanth.storage_limit_bytes
    token = get_company_admin_token(client)

    try:
        # Set storage limit to 10 bytes
        vasanth.storage_limit_bytes = 10
        db.commit()

        # Attempt to upload a document of valid image bytes exceeding 10 bytes quota
        from PIL import Image
        img = Image.new("RGB", (50, 50), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        file_content = buf.getvalue()
        resp = client.post(
            "/api/documents",
            files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 413
        assert "quota exceeded" in resp.json()["detail"].lower()
    finally:
        vasanth.storage_limit_bytes = original_limit
        db.commit()


def test_monthly_ai_budget_enforcement(client, db):
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    original_budget = vasanth.monthly_ai_budget_cents
    token = get_company_admin_token(client)

    # Find a document belonging to Vasanth & Co
    doc = db.query(Document).filter(Document.company_id == vasanth.id, Document.deleted_at.is_(None)).first()
    assert doc is not None

    try:
        # Set monthly budget to 100 cents
        vasanth.monthly_ai_budget_cents = 100
        db.commit()

        # Record a ledger spend of 100 cents for this month
        ledger_entry = AIUsageLedger(
            company_id=vasanth.id,
            branch_id=doc.branch_id,
            provider="gemini",
            model="gemini-2.0-flash",
            operation="ocr",
            tokens_in=500,
            tokens_out=200,
            cost_cents=100,
            status="success",
            created_at=datetime.utcnow(),
        )
        db.add(ledger_entry)
        db.commit()

        # Attempt to reprocess document for OCR
        resp = client.post(
            f"/api/documents/{doc.id}/reprocess",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 402
        assert "monthly ai budget exceeded" in resp.json()["detail"].lower()
    finally:
        vasanth.monthly_ai_budget_cents = original_budget
        db.query(AIUsageLedger).filter(AIUsageLedger.company_id == vasanth.id).delete()
        db.commit()


# ── 3. Platform Dashboard Endpoint ──────────────────────────────────────────

def test_platform_dashboard_endpoint(client, db):
    master_token = get_master_token(client)
    resp = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {master_token}"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "total_companies" in data
    assert "active_companies" in data
    assert "total_branches" in data
    assert "total_users" in data
    assert "total_documents" in data
    assert "total_storage_bytes" in data
    assert "total_ai_spent_cents" in data
    assert "pending_onboardings" in data
    assert "recent_activity" in data
    assert isinstance(data["recent_activity"], list)


# ── 4. Company Details & Quotas Management APIs ──────────────────────────────

def test_company_details_and_update_quotas(client, db):
    master_token = get_master_token(client)
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    assert vasanth is not None

    # 1. GET company details
    get_resp = client.get(
        f"/api/admin/companies/{vasanth.id}",
        headers={"Authorization": f"Bearer {master_token}"},
    )
    assert get_resp.status_code == 200
    details = get_resp.json()
    assert details["id"] == vasanth.id
    assert "max_branches" in details
    assert "storage_used_bytes" in details

    # 2. PUT update company quotas
    update_payload = {
        "max_branches": 12,
        "max_users": 35,
        "storage_limit_bytes": 10 * 1024 * 1024 * 1024,
        "monthly_ai_budget_cents": 5000,
        "mfa_required_for_all": True,
    }
    put_resp = client.put(
        f"/api/admin/companies/{vasanth.id}",
        json=update_payload,
        headers={"Authorization": f"Bearer {master_token}"},
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["max_branches"] == 12
    assert updated["max_users"] == 35
    assert updated["monthly_ai_budget_cents"] == 5000
    assert updated["mfa_required_for_all"] is True

    # 3. Verify audit log was recorded
    audit_entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == MASTER_ADMIN_COMPANY_UPDATE, AuditLog.object_id == str(vasanth.id))
        .first()
    )
    assert audit_entry is not None


# ── 5. System Settings APIs ──────────────────────────────────────────────────

def test_system_settings_api(client, db):
    master_token = get_master_token(client)

    # 1. GET settings
    get_resp = client.get("/api/admin/settings", headers={"Authorization": f"Bearer {master_token}"})
    assert get_resp.status_code == 200
    settings = get_resp.json()
    assert "system_defaults" in settings
    assert "ai_providers" in settings
    assert "mfa_policy" in settings

    # 2. PUT settings (update default quotas and enable a provider)
    update_payload = {
        "system_defaults": {
            "default_max_branches": 8,
            "default_max_users": 25,
            "default_storage_limit_bytes": 10737418240,
            "default_monthly_ai_budget_cents": 3500,
        },
        "ai_providers": {
            "gemini": {"enabled": True, "default_model": "gemini-2.0-flash"},
            "gpt": {"enabled": True, "default_model": "gpt-4o-mini"},
            "claude": {"enabled": False, "default_model": "claude-3-5-sonnet-20241022"},
        },
    }
    put_resp = client.put(
        "/api/admin/settings",
        json=update_payload,
        headers={"Authorization": f"Bearer {master_token}"},
    )
    assert put_resp.status_code == 200

    # 3. GET to verify changes
    verify_resp = client.get("/api/admin/settings", headers={"Authorization": f"Bearer {master_token}"})
    verify_data = verify_resp.json()
    assert verify_data["system_defaults"]["default_max_branches"] == 8
    assert verify_data["ai_providers"]["gpt"]["enabled"] is True


# ── 6. Onboarding Magic Bytes Validation ─────────────────────────────────────

def test_onboarding_magic_bytes_validation(client, db):
    master_token = get_master_token(client)

    # Initiate onboarding
    init_resp = client.post(
        "/api/admin/onboarding/initiate",
        json={
            "company_name": "Magic Bytes Test Co",
            "contact_name": "Validation Tester",
            "contact_email": f"test_{uuid.uuid4().hex[:6]}@validation.test",
        },
        headers={"Authorization": f"Bearer {master_token}"},
    )
    assert init_resp.status_code == 200
    token = init_resp.json()["token"]

    try:
        # Attempt to upload executable/script spoofed as a PDF
        fake_pdf = b"#!/bin/bash\necho 'malicious executable'\n"
        bad_upload = client.post(
            f"/api/onboarding/{token}/upload-document",
            files={"file": ("malicious.pdf", io.BytesIO(fake_pdf), "application/pdf")},
            data={"document_type": "pan_document"},
        )
        assert bad_upload.status_code == 400
        assert "expected format" in bad_upload.json()["detail"].lower() or "signature" in bad_upload.json()["detail"].lower()

        # Upload genuine PDF with valid %PDF magic bytes
        genuine_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        good_upload = client.post(
            f"/api/onboarding/{token}/upload-document",
            files={"file": ("legit.pdf", io.BytesIO(genuine_pdf), "application/pdf")},
            data={"document_type": "pan_document"},
        )
        assert good_upload.status_code == 200
        assert good_upload.json()["document_type"] == "pan_document"
    finally:
        db.query(CompanyOnboarding).filter(CompanyOnboarding.token == token).delete()
        db.commit()


# ── 7. Approved Onboarding Provisions Mandatory MFA and 72h Invite ───────────

def test_approved_onboarding_provisions_mandatory_mfa_and_invitation(client, db):
    master_token = get_master_token(client)
    unique_id = uuid.uuid4().hex[:6]
    admin_email = f"firstadmin.{unique_id}@testtenant.test"
    legal_name = f"Test Tenant {unique_id} Ltd"
    new_company_id = None
    onboarding_id = None

    # Initiate onboarding
    init_resp = client.post(
        "/api/admin/onboarding/initiate",
        json={
            "company_name": f"Test Tenant {unique_id}",
            "contact_name": "First Admin",
            "contact_email": admin_email,
        },
        headers={"Authorization": f"Bearer {master_token}"},
    )
    assert init_resp.status_code == 200
    token = init_resp.json()["token"]
    onboarding_id = init_resp.json()["id"]

    try:
        # Submit application with complete sections A-G
        submit_payload = {
            "legal_company_name": legal_name,
            "trade_name": "Test Tenant",
            "business_type": "Private Limited Company (Pvt Ltd)",
            "business_description": "Cloud document automation.",
            "year_of_establishment": "2022",
            "company_website": "https://testtenant.test",
            "pan_number": "AABCA1234F",
            "gstin": "33AABCA1234F1Z5",
            "gst_type": "Regular",
            "cin": "U72900TN2022PTC123456",
            "udyam_number": "UDYAM-TN-01-0012345",
            "tan": "CHNA12345E",
            "address_line1": "Level 2, Test Park",
            "city": "Chennai",
            "district": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600113",
            "country": "India",
            "auth_contact_name": "First Admin",
            "auth_contact_designation": "Managing Director",
            "auth_contact_email": admin_email,
            "auth_contact_mobile": "9876543210",
            "has_multiple_branches": False,
            "admin_name": "First Admin",
            "admin_email": admin_email,
            "admin_password": "SecurePassword@123",
            "confirm_password": "SecurePassword@123",
            "admin_mobile": "9876543210",
            "admin_designation": "Managing Director",
            "primary_document_types": ["Invoices"],
            "expected_monthly_volume": "100-500",
            "languages": ["English"],
            "timezone": "Asia/Kolkata",
            "currency": "INR",
        }
        sub_resp = client.post(
            f"/api/onboarding/{token}/submit",
            json=submit_payload,
        )
        assert sub_resp.status_code == 200, sub_resp.text

        # Approve onboarding
        approve_resp = client.post(
            f"/api/admin/onboarding/{onboarding_id}/approve",
            headers={"Authorization": f"Bearer {master_token}"},
        )
        assert approve_resp.status_code == 200, approve_resp.text

        # 1. Verify Company has mfa_required_for_all = True
        new_company = db.query(Company).filter(Company.name == legal_name).first()
        assert new_company is not None
        new_company_id = new_company.id
        assert new_company.mfa_required_for_all is True

        # 2. Verify Invitation was created with 72h expiry
        invitation = (
            db.query(Invitation)
            .filter(Invitation.company_id == new_company_id, Invitation.email == admin_email)
            .first()
        )
        assert invitation is not None
        assert invitation.expires_at > datetime.utcnow() + timedelta(hours=70)
        assert invitation.invited_role == UserRole.GLOBAL_ADMIN
    finally:
        # Cleanup
        if admin_email:
            db.query(Invitation).filter(Invitation.email == admin_email).delete()
            user = db.query(User).filter(User.email == admin_email).first()
            if user:
                db.delete(user)
        if new_company_id:
            db.query(Branch).filter(Branch.company_id == new_company_id).delete()
            comp = db.query(Company).filter(Company.id == new_company_id).first()
            if comp:
                db.delete(comp)
        if onboarding_id:
            db.query(CompanyOnboarding).filter(CompanyOnboarding.id == onboarding_id).delete()
        db.commit()
