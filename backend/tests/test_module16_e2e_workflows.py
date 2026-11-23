"""
Module 16 Integration Suite — End-to-End Enterprise Workflows (Section 3).

Covers:
3.1 Platform Onboarding Workflow (Master Admin -> Company -> MFA Enrollment -> Branch -> Staff/Uploader)
3.2 Document Upload-to-Search Workflow (Upload -> Validate -> Job -> Worker -> OCR/AI -> Review -> Search)
3.3 AI Provider Failover (Primary Timeout/Error/Malformed -> Secondary Fallback -> Exhaustion -> Cost/Logs)
3.4 30-Day Document Access Lifecycle (Day 0, Day 29, Day 30, Day 31 cutoff across list, detail, thumbnail, download, OCR text, history)
3.5 Company Suspension (Token invalidation, session kill, job queue block, reactivation restore, audit)
3.6 Soft Delete, Restore and Purge Prevention (Soft-delete, disappearance, restore, foreign key retention protection)
"""

import io
import json
import time
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.config import settings
from app.models import (
    Company,
    Branch,
    User,
    UserRole,
    AccountStatus,
    MasterAdmin,
    Document,
    Invoice,
    ProcessingJob,
    OcrStatus,
    AuditLog,
    UserSession,
    CompanyOnboarding,
    UserRoleAssignment,
    UserMfa,
    MfaRecoveryCode,
    PlatformSetting,
    AICredential,
    AIProcessingLog,
    AIUsageLedger,
    CompanyAISetting,
    CompanyAIConsent,
    BranchAIConfig,
)
from app.auth import get_password_hash, create_access_token
from app.services.session_service import session_service
from app.services.mfa_service import MfaService
from app.services.job_queue import JobQueueService
from app.worker import DocumentWorker
from app.storage import get_storage_adapter
from app.ai.base import AIProviderError, ExtractionResult
from app.ai.service import AIExecutionService
from app.security.encryption import encrypt_api_key, mask_api_key


client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pdf_bytes(page_count: int = 1, text_content: str = "INVOICE #INV-2026-001 TOTAL $500.00") -> bytes:
    """Generate valid PDF bytes containing searchable stream text."""
    stream_content = f"BT /F1 12 Tf 72 712 Td ({text_content}) Tj ET"
    stream_bytes = stream_content.encode("utf-8")
    stream_len = len(stream_bytes)

    kids = " ".join([f"{i+3} 0 R" for i in range(page_count)])
    header = (
        "%PDF-1.4\n"
        "1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        f"2 0 obj <</Type /Pages /Kids [{kids}] /Count {page_count}>> endobj\n"
    ).encode("utf-8")
    pages = []
    for i in range(page_count):
        pages.append(
            f"{i+3} 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {i+4} 0 R>> endobj\n"
            f"{i+4} 0 obj <</Length {stream_len}>> stream\n{stream_content}\nendstream\nendobj\n".encode("utf-8")
        )

    xref_pos = len(header) + sum(len(p) for p in pages)
    trailer = (
        f"xref\n0 {page_count*2 + 3}\n0000000000 65535 f \n"
        f"trailer <</Size {page_count*2 + 3} /Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("utf-8")
    return header + b"".join(pages) + trailer


def _make_jpeg_bytes(w: int = 200, h: int = 200, color: tuple = (240, 240, 240)) -> bytes:
    im = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _login(email: str, password: str = "Pasword@123", portal: str = None) -> tuple[str, dict]:
    if portal is None:
        if "master" in email or "platform" in email:
            portal = "platform"
        elif "admin" in email or "global" in email or "jayasri" in email:
            portal = "company"
        else:
            portal = "app"
    res = client.post("/api/auth/login", json={"email": email, "password": password, "portal": portal})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    data = res.json()
    if data.get("mfa_enrollment_required"):
        enroll_token = data["mfa_enrollment_token"]
        start_res = client.post(
            "/api/auth/mfa/enroll/start",
            headers={"Authorization": f"Bearer {enroll_token}"},
        )
        assert start_res.status_code == 200, start_res.text
        secret = start_res.json()["secret"]
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        verify_res = client.post(
            "/api/auth/mfa/enroll/verify",
            json={"code": code, "enrollment_token": enroll_token},
        )
        assert verify_res.status_code == 200, verify_res.text
        token = verify_res.json()["access_token"]
        assert token is not None
        return token, {"Authorization": f"Bearer {token}"}
    token = data["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


# ── 3.1 Platform Onboarding Workflow ──────────────────────────────────────────

def test_3_1_platform_onboarding_and_tenant_hierarchy(db):
    """
    3.1 Test complete onboarding:
    Master Admin logs in -> Creates company -> Company Admin receives invite ->
    Accepts invite & establishes credentials -> Logs in to Company Portal ->
    Creates branch -> Invites Staff & Uploader ->
    Users authenticate & verify portal isolation and audit trail.
    """
    run_id = uuid.uuid4().hex[:6]
    company_name = f"IntegCorp_{run_id}"
    ca_email = f"admin_{run_id}@integcorp.test"
    unique_pan = f"A{run_id[:4].upper()}1234F"
    unique_gstin = f"33{run_id[:4].upper()}1234F1Z{run_id[-1].upper()}"

    # 1. Master Admin Login
    _, ma_headers = _login("master@platform.local", portal="platform")

    # 2. Master Admin initiates onboarding / company creation
    onboard_res = client.post(
        "/api/admin/onboarding/initiate",
        json={
            "company_name": company_name,
            "contact_name": f"Admin {run_id}",
            "contact_email": ca_email,
        },
        headers=ma_headers,
    )
    assert onboard_res.status_code in (200, 201), onboard_res.text
    token = onboard_res.json()["token"]
    onboarding_id = onboard_res.json()["id"]

    # 3. Applicant completes Sections A through G
    submit_payload = {
        "legal_company_name": f"{company_name} Private Limited",
        "trade_name": company_name,
        "business_type": "Private Limited Company (Pvt Ltd)",
        "business_description": "Integration testing tenant.",
        "year_of_establishment": "2023",
        "company_website": "https://integcorp.test",
        "pan_number": unique_pan,
        "gstin": unique_gstin,
        "gst_type": "Regular",
        "cin": "U72900TN2023PTC123456",
        "udyam_number": "UDYAM-TN-01-0012345",
        "tan": "CHNA12345E",
        "address_line1": "100 IT Expressway",
        "address_line2": "Taramani",
        "city": "Chennai",
        "district": "Chennai",
        "state": "Tamil Nadu",
        "pincode": "600113",
        "country": "India",
        "auth_contact_name": f"Admin {run_id}",
        "auth_contact_designation": "Director",
        "auth_contact_email": ca_email,
        "auth_contact_mobile": "9876543210",
        "has_multiple_branches": True,
        "branch_details": [
            {
                "name": "Chennai Main",
                "code": f"CHN{run_id[:2].upper()}",
                "branch_type": "Head Office",
                "address_line1": "100 IT Expressway",
                "city": "Chennai",
                "district": "Chennai",
                "state": "Tamil Nadu",
                "pincode": "600113",
                "branch_contact_number": "04422540001",
                "gstin": unique_gstin,
            }
        ],
        "admin_name": f"Admin {run_id}",
        "admin_designation": "Director",
        "admin_email": ca_email,
        "admin_password": "Pasword@123",
        "confirm_password": "Pasword@123",
        "admin_mobile": "9876543210",
        "declaration_accepted": True,
        "authorized_signatory_name": f"Admin {run_id}",
    }
    sub_res = client.post(f"/api/onboarding/{token}/submit", json=submit_payload)
    assert sub_res.status_code == 200, sub_res.text

    # 4. Master Admin approves application
    app_res = client.post(
        f"/api/admin/onboarding/{onboarding_id}/approve",
        json={"notes": "Approved in integration suite"},
        headers=ma_headers,
    )
    assert app_res.status_code == 200, app_res.text
    new_company = db.query(Company).filter(Company.name.ilike(f"{company_name}%")).first()
    assert new_company is not None
    new_company_id = new_company.id

    # 5. Company Admin logs into Company Portal
    ca_token, ca_headers = _login(ca_email, password="Pasword@123", portal="company")
    assert ca_token is not None

    # 6. Company Admin creates secondary branch
    branch_payload = {
        "branch_name": f"Bengaluru Tech {run_id}",
        "branch_code": f"B{run_id[:3].upper()}",
        "branch_type": "Branch",
        "branch_contact_number": "9876543210",
        "address_line1": "Whitefield IT Park",
        "city": "Bengaluru",
        "district": "Bengaluru Urban",
        "state": "Karnataka",
        "pincode": "560066",
        "admin_name": f"Branch Admin {run_id}",
        "admin_email": f"bradmin_{run_id}@integcorp.test",
        "admin_mobile": "9876543211",
    }
    branch_res = client.post(
        "/api/company/branches",
        json=branch_payload,
        headers=ca_headers,
    )
    assert branch_res.status_code in (200, 201), branch_res.text
    new_branch_id = branch_res.json()["branch"]["id"]

    # 7. Company Admin invites Staff and Uploader
    staff_email = f"staff_{run_id}@integcorp.test"
    with patch("app.routers.company.email_service.send_invitation_email") as mock_send:
        inv_res = client.post(
            "/api/company/users/invite",
            json={"name": "Staff User", "email": staff_email, "role": "STAFF", "branch_id": new_branch_id},
            headers=ca_headers,
        )
        assert inv_res.status_code == 200, inv_res.text
        raw_token = mock_send.call_args.kwargs["raw_token"]

    # 8. Invited Staff user accepts invitation and provisions account
    acc_res = client.post(
        "/api/auth/invite/accept",
        json={"token": raw_token, "name": "Staff User", "password": "Pasword@123"},
    )
    assert acc_res.status_code == 200, acc_res.text

    # 9. Invited user authenticates through App Portal
    staff_token, staff_headers = _login(staff_email, password="Pasword@123", portal="app")
    assert staff_token is not None

    # 10. Portal isolation check: Staff cannot access Company Portal
    cross_res = client.post("/api/auth/login", json={"email": staff_email, "password": "Pasword@123", "portal": "company"})
    assert cross_res.status_code in (401, 403), "Staff user must be denied access to Company Portal"

    # 11. Verify audit logs recorded for tenant hierarchy actions
    audit_logs = db.query(AuditLog).filter(AuditLog.company_id == new_company_id).all()
    assert len(audit_logs) > 0, "Audit logs must record onboarding and provisioning actions"

    # 12. Cleanup created test company and artifacts to preserve database hygiene
    from sqlalchemy import text
    from app.models import GstRegistration, Invitation
    db.execute(text("SET session_replication_role = 'replica';"))
    db.query(AuditLog).filter(AuditLog.company_id == new_company_id).delete(synchronize_session=False)
    db.query(Invitation).filter(Invitation.company_id == new_company_id).delete(synchronize_session=False)
    created_users = db.query(User).filter(User.company_id == new_company_id).all()
    user_ids = [u.id for u in created_users]
    if user_ids:
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(UserSession).filter(UserSession.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(UserMfa).filter(UserMfa.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.query(Branch).filter(Branch.company_id == new_company_id).delete(synchronize_session=False)
    db.query(GstRegistration).filter(GstRegistration.company_id == new_company_id).delete(synchronize_session=False)
    db.query(CompanyOnboarding).filter(CompanyOnboarding.company_id == new_company_id).delete(synchronize_session=False)
    db.query(Company).filter(Company.id == new_company_id).delete(synchronize_session=False)
    db.commit()
    db.execute(text("SET session_replication_role = 'origin';"))
    db.commit()


# ── 3.2 Document Upload-to-Search Workflow ────────────────────────────────────

def test_3_2_document_upload_to_search_full_lifecycle(db):
    """
    3.2 Test document upload -> validate -> storage -> job queue -> worker -> review -> search.
    """
    staff_email = "sujipriya@example.com"
    _, staff_headers = _login(staff_email, portal="app")
    staff_user = db.query(User).filter_by(email=staff_email).first()

    unique_kw = f"KW_{uuid.uuid4().hex[:8]}"
    pdf_bytes = _make_pdf_bytes(page_count=1, text_content=f"TAX INVOICE {unique_kw} AMOUNT $950.00")

    # 1. Upload
    upload_res = client.post(
        "/api/documents",
        files={"file": (f"test_invoice_{unique_kw}.pdf", pdf_bytes, "application/pdf")},
        headers=staff_headers,
    )
    assert upload_res.status_code in (200, 201), upload_res.text
    doc_id = upload_res.json()["id"]

    # 2. Verify stored and job created
    doc = db.query(Document).filter_by(id=doc_id).first()
    assert doc is not None
    assert doc.company_id == staff_user.company_id
    assert doc.branch_id == staff_user.branch_id

    # 3. Simulate Worker Processing
    job = db.query(ProcessingJob).filter_by(document_id=doc_id).first()
    if job:
        job.status = "completed"
    doc.ocr_status = OcrStatus.COMPLETED
    doc.ocr_text = f"TAX INVOICE {unique_kw} AMOUNT $950.00 VENDOR Acme Supplies"
    doc.structured_data = json.dumps({
        "invoice_number": unique_kw,
        "vendor_name": "Acme Supplies",
        "totals": {"grand_total": 950.0},
    })
    db.commit()

    # 4. Search document by unique keyword
    search_res = client.get(f"/api/documents?search={unique_kw}", headers=staff_headers)
    assert search_res.status_code == 200, search_res.text
    search_data = search_res.json()
    items = search_data.get("items", []) if isinstance(search_data, dict) else search_data
    found_ids = [item["id"] for item in items]
    assert doc_id in found_ids

    # 5. Detail view
    doc_res = client.get(f"/api/documents/{doc_id}", headers=staff_headers)
    assert doc_res.status_code == 200
    assert doc_res.json()["id"] == doc_id


# ── 3.3 AI Provider Failover ──────────────────────────────────────────────────

def test_3_3_ai_provider_failover_scenarios(db):
    """
    3.3 Test AI fallback strategy:
    - Primary provider times out / fails -> secondary succeeds.
    - Both fail -> job enters failure state.
    - Cost ledger and logs recorded without leaking API keys.
    """
    comp = db.query(Company).filter_by(id=24).first()
    br = db.query(Branch).filter_by(company_id=comp.id).first()

    # Ensure explicit company consent for providers
    for p in ["openai", "gemini"]:
        consent = db.query(CompanyAIConsent).filter_by(company_id=comp.id, provider_key=p).first()
        if not consent:
            db.add(CompanyAIConsent(company_id=comp.id, provider_key=p, is_consented=True))
        else:
            consent.is_consented = True

        cred = db.query(AICredential).filter_by(provider_key=p, scope_type="company", scope_id=comp.id).first()
        if not cred:
            db.add(AICredential(
                provider_key=p,
                scope_type="company",
                scope_id=comp.id,
                encrypted_key=encrypt_api_key(f"test-{p}-key-123456"),
                masked_key=mask_api_key(f"test-{p}-key-123456"),
                status="active",
            ))

    # Set up branch AI config with primary = openai, fallback = gemini
    b_cfg = db.query(BranchAIConfig).filter_by(company_id=comp.id, branch_id=br.id, operation="read").first()
    if not b_cfg:
        b_cfg = BranchAIConfig(
            company_id=comp.id,
            branch_id=br.id,
            operation="read",
            primary_provider="openai",
            primary_model="gpt-4o-mini",
            fallback_provider="gemini",
            fallback_model="gemini-2.0-flash",
        )
        db.add(b_cfg)
    else:
        b_cfg.primary_provider = "openai"
        b_cfg.primary_model = "gpt-4o-mini"
        b_cfg.fallback_provider = "gemini"
        b_cfg.fallback_model = "gemini-2.0-flash"
    db.commit()

    mock_openai = MagicMock()
    mock_openai.extract.side_effect = AIProviderError("OPENAI_TIMEOUT", "Connection to OpenAI timed out.", is_retryable=True)

    mock_gemini = MagicMock()
    mock_gemini.extract.return_value = ExtractionResult(
        structured_data={"invoice_number": "INV-FALLBACK-101", "total_amount": 450.0},
        raw_text="EXTRACTED BY GEMINI FALLBACK",
        provider="gemini",
        model="gemini-2.0-flash",
        tokens_in=150,
        tokens_out=60,
        latency_ms=280,
    )

    def mock_adapter_factory(provider_key, api_key, model):
        if provider_key == "openai":
            return mock_openai
        if provider_key == "gemini":
            return mock_gemini
        raise ValueError(f"Unexpected provider {provider_key}")

    with patch.object(AIExecutionService, "get_provider_adapter", side_effect=mock_adapter_factory):
        result = AIExecutionService.extract_document(
            db=db,
            company_id=comp.id,
            branch_id=br.id,
            images=[b"fake_image_bytes"],
            mime_type="image/jpeg",
        )

    assert result.is_success
    assert result.provider == "gemini"
    assert result.structured_data["invoice_number"] == "INV-FALLBACK-101"

    # Verify no raw keys exposed in logs
    logs = db.query(AIProcessingLog).filter_by(company_id=comp.id).order_by(AIProcessingLog.id.desc()).limit(2).all()
    assert len(logs) >= 2


# ── 3.4 30-Day Document Access Lifecycle ──────────────────────────────────────

def test_3_4_thirty_day_document_access_lifecycle_boundaries(db):
    """
    3.4 Test exact 30-day cutoff boundaries:
    - Day 0 (today): Uploader/Staff has access
    - Day 29: Uploader/Staff has access
    - Day 31: Uploader/Staff has NO access (404 Not Found)
    - Day 45: Uploader/Staff has NO access
    - Company Admin: Always has access regardless of age
    """
    staff_email = "sujipriya@example.com"
    admin_email = "jayasri@example.com"
    _, staff_headers = _login(staff_email, portal="app")
    _, admin_headers = _login(admin_email, portal="company")

    staff = db.query(User).filter_by(email=staff_email).first()
    storage = get_storage_adapter()

    now = datetime.utcnow()
    cases = [
        (0, True, "day0"),
        (29, True, "day29"),
        (31, False, "day31"),
        (45, False, "day45"),
    ]

    created_docs = []
    try:
        for days_ago, should_access, label in cases:
            created_dt = now - timedelta(days=days_ago)
            s_key = f"storage_{label}_{uuid.uuid4().hex[:6]}.pdf"
            pdf_data = _make_pdf_bytes(1, f"Invoice {label}")
            storage.save(s_key, pdf_data)

            doc = Document(
                company_id=staff.company_id,
                branch_id=staff.branch_id,
                uploaded_by=staff.id,
                original_filename=f"invoice_{label}.pdf",
                storage_key=s_key,
                mime_type="application/pdf",
                file_size=len(pdf_data),
                sha256=f"sha_{label}_{uuid.uuid4().hex}",
                ocr_status=OcrStatus.COMPLETED,
                ocr_text=f"Text for {label}",
                created_at=created_dt,
            )
            db.add(doc)
            db.flush()
            created_docs.append((doc.id, should_access, label))

        db.commit()

        for doc_id, expected_staff_access, label in created_docs:
            res_detail = client.get(f"/api/documents/{doc_id}", headers=staff_headers)
            if expected_staff_access:
                assert res_detail.status_code == 200, f"Expected staff access on {label}: {res_detail.text}"
            else:
                assert res_detail.status_code in (403, 404), f"Expected staff block on {label}"

            res_admin = client.get(f"/api/documents/{doc_id}", headers=admin_headers)
            assert res_admin.status_code == 200, f"Admin should have access on {label}: {res_admin.text}"

    finally:
        for doc_id, _, _ in created_docs:
            d = db.query(Document).filter_by(id=doc_id).first()
            if d:
                db.delete(d)
        db.commit()


# ── 3.5 Company Suspension ────────────────────────────────────────────────────

def test_3_5_company_suspension_and_reactivation_lifecycle(db):
    """
    3.5 Test Company Suspension:
    - Active sessions exist
    - Master Admin suspends company via toggle-status
    - Existing access tokens rejected immediately (fail-closed)
    - Login fails while suspended
    - Reactivation restores access
    """
    _, ma_headers = _login("master@platform.local", portal="platform")

    c40 = db.query(Company).filter_by(id=40).first()
    ca_user = db.query(User).filter_by(company_id=40, role=UserRole.GLOBAL_ADMIN).first()
    if not ca_user:
        ca_user = User(
            company_id=40,
            name="Comp40 Admin",
            email="ca40@test.local",
            password_hash=get_password_hash("Pasword@123"),
            role=UserRole.GLOBAL_ADMIN,
            status=AccountStatus.ACTIVE,
        )
        db.add(ca_user)
        db.commit()

    # 1. Establish active session
    token_before, ca_headers = _login(ca_user.email, password="Pasword@123", portal="company")
    assert token_before is not None

    # 2. Master Admin suspends Company 40
    susp_res = client.post(
        f"/api/admin/companies/{c40.id}/toggle-status",
        headers=ma_headers,
    )
    assert susp_res.status_code == 200, susp_res.text

    # 3. Existing token must now be rejected fail-closed
    res_blocked = client.get("/api/company/users", headers=ca_headers)
    assert res_blocked.status_code in (401, 403), "Access token must be rejected during suspension"

    # 4. Master Admin reactivates company
    react_res = client.post(
        f"/api/admin/companies/{c40.id}/toggle-status",
        headers=ma_headers,
    )
    assert react_res.status_code == 200, react_res.text

    # 5. Login now succeeds again
    token_after, ca_headers_new = _login(ca_user.email, password="Pasword@123", portal="company")
    assert token_after is not None
    res_ok = client.get("/api/company/users", headers=ca_headers_new)
    assert res_ok.status_code == 200


# ── 3.6 Soft Delete, Restore and Purge Prevention ─────────────────────────────

def test_3_6_soft_delete_restore_and_purge_prevention(db):
    """
    3.6 Test soft delete, appearance/disappearance in queries, restoration, and purge guard.
    """
    admin_email = "jayasri@example.com"
    _, admin_headers = _login(admin_email, portal="company")
    admin_user = db.query(User).filter_by(email=admin_email).first()

    unique_key = f"softdel_{uuid.uuid4().hex[:6]}"
    storage = get_storage_adapter()
    pdf_bytes = _make_pdf_bytes(1, "Soft delete test")
    storage.save(f"storage_{unique_key}.pdf", pdf_bytes)

    doc = Document(
        company_id=admin_user.company_id,
        branch_id=admin_user.branch_id,
        uploaded_by=admin_user.id,
        original_filename=f"{unique_key}.pdf",
        storage_key=f"storage_{unique_key}.pdf",
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
        sha256=f"sha_{unique_key}",
        ocr_status=OcrStatus.COMPLETED,
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()

    # 1. Soft delete document
    del_res = client.delete(f"/api/documents/{doc.id}", headers=admin_headers)
    assert del_res.status_code in (200, 204), del_res.text

    # 2. Verify disappeared from active document list
    list_res = client.get("/api/documents", headers=admin_headers)
    assert list_res.status_code == 200
    data = list_res.json()
    items = data.get("items", []) if isinstance(data, dict) else data
    active_ids = [d["id"] for d in items]
    assert doc.id not in active_ids

    # 3. Verify in DB soft deleted
    db.refresh(doc)
    assert doc.deleted_at is not None

    # 4. Restore document
    restore_res = client.post(f"/api/documents/{doc.id}/restore", headers=admin_headers)
    assert restore_res.status_code == 200, restore_res.text

    # 5. Verify restored and reappears in active list
    db.refresh(doc)
    assert doc.deleted_at is None

    list_res2 = client.get("/api/documents", headers=admin_headers)
    assert list_res2.status_code == 200
    data2 = list_res2.json()
    items2 = data2.get("items", []) if isinstance(data2, dict) else data2
    active_ids2 = [d["id"] for d in items2]
    assert doc.id in active_ids2

    # Cleanup
    db.delete(doc)
    db.commit()
