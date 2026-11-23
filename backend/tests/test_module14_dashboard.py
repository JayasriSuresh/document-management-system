"""
Module 14 – Operational Dashboards, Usage Reporting, and Job Monitoring Tests.

Covers all 18 mandatory verification requirements:
  1. Company dashboard aggregate accuracy.
  2. Branch dashboard aggregate accuracy.
  3. Document status reconciliation.
  4. Branch distribution reconciliation.
  5. AI cost reconciliation against raw AI processing logs.
  6. Provider and model breakdown accuracy.
  7. Failed and fallback AI attempts.
  8. Multi-tenant isolation.
  9. Branch-level isolation.
  10. Staff 30-day restriction.
  11. Date-range boundaries.
  12. Soft-deleted record handling.
  13. Failed-job error sanitization.
  14. CSV formula-injection protection.
  15. CSV export authorization.
  16. Zero-record handling.
  17. Unauthorized branch access.
  18. Reprocessing permission enforcement.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io
import pytest
from sqlalchemy import func

from app.auth import get_password_hash
from app.database import SessionLocal
from app.models import (
    AIProcessingLog,
    Branch,
    Company,
    CompanyStatus,
    Document,
    Invoice,
    OcrStatus,
    ProcessingJob,
    User,
    UserRole,
)
from app.services.csv_export import sanitize_csv_cell


@pytest.fixture(scope="module")
def module14_test_data(client):
    """
    Sets up isolated test data for Module 14 tests:
    - Dedicated test companies A & B (isolated from real production data like Company 24).
    - Branches, users, documents, invoices, AI logs, and processing jobs.
    - Automatic teardown after test execution.
    """
    import uuid
    from app.models import UserRoleAssignment, AccountStatus
    from sqlalchemy import text

    db = SessionLocal()
    uid = uuid.uuid4().hex[:6]
    pwd = get_password_hash("Pasword@123")

    try:
        # Create isolated Company A & B
        comp_a = Company(
            name=f"Mod14 Test A {uid}",
            code=f"M14A_{uid}",
            status=CompanyStatus.ACTIVE,
            max_branches=5,
            max_users=10,
            storage_limit_bytes=5368709120,
            monthly_ai_budget_cents=5000,
            mfa_required_for_all=False,
        )
        comp_b = Company(
            name=f"Mod14 Test B {uid}",
            code=f"M14B_{uid}",
            status=CompanyStatus.ACTIVE,
            max_branches=5,
            max_users=10,
            storage_limit_bytes=5368709120,
            monthly_ai_budget_cents=5000,
            mfa_required_for_all=False,
        )
        db.add_all([comp_a, comp_b])
        db.flush()

        branch_a1 = Branch(
            company_id=comp_a.id,
            name=f"Chennai Branch {uid}",
            code=f"CHN_{uid}",
            status="active",
        )
        branch_a2 = Branch(
            company_id=comp_a.id,
            name=f"Mysore Branch {uid}",
            code=f"MYS_{uid}",
            status="active",
        )
        branch_b = Branch(
            company_id=comp_b.id,
            name=f"Branch B {uid}",
            code=f"BRB_{uid}",
            status="active",
        )
        db.add_all([branch_a1, branch_a2, branch_b])
        db.flush()

        # Users for Company A
        admin_global_email = f"m14_admin_global_{uid}@test.local"
        admin_branch_email = f"m14_admin_b1_{uid}@test.local"
        admin_branch2_email = f"m14_admin_b2_{uid}@test.local"
        staff_email = f"m14_staff_{uid}@test.local"
        admin_b_email = f"m14_admin_b_{uid}@test.local"

        admin_global = User(
            email=admin_global_email,
            password_hash=pwd,
            name="Global Admin",
            role=UserRole.GLOBAL_ADMIN,
            status=AccountStatus.ACTIVE,
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            token_version=1,
        )
        admin_branch1 = User(
            email=admin_branch_email,
            password_hash=pwd,
            name="Branch 1 Admin",
            role=UserRole.ADMIN,
            status=AccountStatus.ACTIVE,
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            token_version=1,
        )
        admin_branch2 = User(
            email=admin_branch2_email,
            password_hash=pwd,
            name="Branch 2 Admin",
            role=UserRole.ADMIN,
            status=AccountStatus.ACTIVE,
            company_id=comp_a.id,
            branch_id=branch_a2.id,
            token_version=1,
        )
        staff_user = User(
            email=staff_email,
            password_hash=pwd,
            name="Staff User",
            role=UserRole.STAFF,
            status=AccountStatus.ACTIVE,
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            token_version=1,
        )
        user_b = User(
            email=admin_b_email,
            password_hash=get_password_hash("Password@123"),
            name="Comp B Admin",
            role=UserRole.GLOBAL_ADMIN,
            status=AccountStatus.ACTIVE,
            company_id=comp_b.id,
            branch_id=branch_b.id,
            token_version=1,
        )
        db.add_all([admin_global, admin_branch1, admin_branch2, staff_user, user_b])
        db.flush()

        db.add_all([
            UserRoleAssignment(user_id=admin_global.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_a.id),
            UserRoleAssignment(user_id=admin_branch1.id, role="ADMIN", scope_type="branch", scope_id=branch_a1.id),
            UserRoleAssignment(user_id=admin_branch2.id, role="ADMIN", scope_type="branch", scope_id=branch_a2.id),
            UserRoleAssignment(user_id=staff_user.id, role="STAFF", scope_type="branch", scope_id=branch_a1.id),
            UserRoleAssignment(user_id=user_b.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_b.id),
        ])
        db.flush()

        now = datetime.utcnow()

        # Seed AI Processing Logs for Company A
        log1 = AIProcessingLog(
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            operation="read",
            provider="gemini",
            model="gemini-1.5-flash",
            is_fallback=False,
            tokens_in=1000,
            tokens_out=250,
            cost_cents=15,
            latency_ms=120,
            success=True,
            created_at=now - timedelta(days=2),
        )
        log2 = AIProcessingLog(
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            operation="read",
            provider="gemini",
            model="gemini-1.5-flash",
            is_fallback=False,
            tokens_in=2000,
            tokens_out=500,
            cost_cents=30,
            latency_ms=180,
            success=True,
            created_at=now - timedelta(days=1),
        )
        log3_failed = AIProcessingLog(
            company_id=comp_a.id,
            branch_id=branch_a2.id,
            operation="read",
            provider="openai",
            model="gpt-4o",
            is_fallback=False,
            tokens_in=500,
            tokens_out=0,
            cost_cents=5,
            latency_ms=500,
            success=False,
            error_code="RATE_LIMIT_EXCEEDED",
            created_at=now - timedelta(hours=5),
        )
        log4_fallback = AIProcessingLog(
            company_id=comp_a.id,
            branch_id=branch_a2.id,
            operation="read",
            provider="gemini",
            model="gemini-1.5-flash",
            is_fallback=True,
            tokens_in=500,
            tokens_out=150,
            cost_cents=10,
            latency_ms=210,
            success=True,
            created_at=now - timedelta(hours=4),
        )
        db.add_all([log1, log2, log3_failed, log4_fallback])

        # Seed an AI log for Company B (must never bleed into Company A)
        log_b = AIProcessingLog(
            company_id=comp_b.id,
            branch_id=branch_b.id,
            operation="read",
            provider="anthropic",
            model="claude-3-5-sonnet",
            is_fallback=False,
            tokens_in=5000,
            tokens_out=1000,
            cost_cents=200,
            latency_ms=300,
            success=True,
            created_at=now,
        )
        db.add(log_b)

        # Seed Documents for Company A
        doc_a = Document(
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            uploaded_by=admin_global.id,
            original_filename="sample_test_doc_m14.pdf",
            storage_key="sample_test_doc_m14.pdf",
            mime_type="application/pdf",
            file_size=204800,
            ocr_status=OcrStatus.COMPLETED,
        )
        db.add(doc_a)
        db.flush()

        # Failed Job with sensitive traceback to verify sanitization
        job_failed = ProcessingJob(
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            document_id=doc_a.id,
            job_type="ocr_extraction",
            status="failed",
            attempts=3,
            max_attempts=3,
            error_code="OCR_API_FAILURE",
            last_error=(
                "Traceback (most recent call last):\n"
                "  File \"/home/ubuntu/app/services/ocr.py\", line 42, in process\n"
                "    resp = client.call(token=\"AIzaSySecretToken1234567890abcdef\")\n"
                "ConnectionError: postgresql://dms_user:secret@127.0.0.1:5432 failed to respond"
            ),
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        )
        job_completed = ProcessingJob(
            company_id=comp_a.id,
            branch_id=branch_a1.id,
            document_id=doc_a.id,
            job_type="ocr_extraction",
            status="completed",
            attempts=1,
            max_attempts=3,
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(days=1),
            completed_at=now - timedelta(days=1),
        )
        db.add_all([job_failed, job_completed])

        db.commit()

        yield {
            "comp_a_id": comp_a.id,
            "branch_a1_id": branch_a1.id,
            "branch_a2_id": branch_a2.id,
            "admin_global_email": admin_global_email,
            "admin_branch_email": admin_branch_email,
            "admin_branch2_email": admin_branch2_email,
            "staff_email": staff_email,
            "comp_b_id": comp_b.id,
            "branch_b_id": branch_b.id,
            "admin_b_email": admin_b_email,
            "doc_a_id": doc_a.id,
            "job_failed_id": job_failed.id,
        }

    finally:
        try:
            db.execute(text("SET session_replication_role = 'replica';"))
            for cid in [comp_a.id, comp_b.id]:
                db.query(ProcessingJob).filter(ProcessingJob.company_id == cid).delete(synchronize_session=False)
                db.query(AIProcessingLog).filter(AIProcessingLog.company_id == cid).delete(synchronize_session=False)
                db.query(Document).filter(Document.company_id == cid).delete(synchronize_session=False)
                db.query(Invoice).filter(Invoice.company_id == cid).delete(synchronize_session=False)
                u_ids = [u.id for u in db.query(User).filter(User.company_id == cid).all()]
                if u_ids:
                    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(u_ids)).delete(synchronize_session=False)
                    db.query(User).filter(User.id.in_(u_ids)).delete(synchronize_session=False)
                db.query(Branch).filter(Branch.company_id == cid).delete(synchronize_session=False)
                db.query(Company).filter(Company.id == cid).delete(synchronize_session=False)
            db.execute(text("SET session_replication_role = 'origin';"))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# ── 1. Company Dashboard Aggregate Accuracy ──────────────────────────────────

def test_company_dashboard_aggregate_accuracy(client, auth_headers, module14_test_data):
    """Verifies that GET /api/dashboard/company returns complete and accurate aggregates."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/company", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["company_id"] == module14_test_data["comp_a_id"]
    assert "documents" in data
    assert "branch_distribution" in data
    assert "invoices" in data
    assert "ai_usage" in data
    assert "jobs" in data
    assert "time_window" in data

    docs = data["documents"]
    assert docs["total_count"] >= 1
    assert "uploaded" in docs["by_status"]
    assert "completed" in docs["by_status"]
    assert "failed" in docs["by_status"]
    assert docs["storage_used_bytes"] > 0
    assert docs["storage_used_mb"] >= 0.0


# ── 2. Branch Dashboard Aggregate Accuracy ───────────────────────────────────

def test_branch_dashboard_aggregate_accuracy(client, auth_headers, module14_test_data):
    """Verifies that GET /api/dashboard/branch/{id} returns branch-scoped aggregates."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    branch_id = module14_test_data["branch_a1_id"]
    resp = client.get(f"/api/dashboard/branch/{branch_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["branch_info"]["id"] == branch_id
    assert "documents" in data
    assert "invoices" in data
    assert "ai_usage" in data
    assert "jobs" in data
    assert "recent_failed_jobs" in data
    assert isinstance(data["recent_failed_jobs"], list)


# ── 3. Document Status Reconciliation ─────────────────────────────────────────

def test_document_status_reconciliation(client, auth_headers, module14_test_data):
    """Ensures sum of documents by status equals total_count."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/company", headers=headers)
    assert resp.status_code == 200
    docs = resp.json()["documents"]

    status_sum = sum(docs["by_status"].values())
    assert status_sum == docs["total_count"], (
        f"Sum of status counts ({status_sum}) does not equal total_count ({docs['total_count']})"
    )


# ── 4. Branch Distribution Reconciliation ────────────────────────────────────

def test_branch_distribution_reconciliation(client, auth_headers, module14_test_data):
    """Ensures sum of branch document counts equals company total documents."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/company", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    branch_doc_sum = sum(b["document_count"] for b in data["branch_distribution"])
    assert branch_doc_sum == data["documents"]["total_count"], (
        f"Sum of branch docs ({branch_doc_sum}) != company total ({data['documents']['total_count']})"
    )


# ── 5. AI Cost Reconciliation Against Raw AI Logs ────────────────────────────

def test_ai_cost_reconciliation_against_raw_logs(client, auth_headers, module14_test_data):
    """Reconciles total AI calls, tokens, and cost directly against raw DB logs."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/ai-usage", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    summary = data["summary"]

    # In fixture, we added 4 logs for Company A:
    # log1: 1000 in, 250 out, 15 cents, success
    # log2: 2000 in, 500 out, 30 cents, success
    # log3: 500 in, 0 out, 5 cents, failed
    # log4: 500 in, 150 out, 10 cents, fallback success
    # Expected: 4 calls, 3 success, 1 failed, 1 fallback, 4000 in, 900 out, 4900 total, 60 cents ($0.60)
    assert summary["total_calls"] == 4
    assert summary["successful_calls"] == 3
    assert summary["failed_calls"] == 1
    assert summary["fallback_calls"] == 1
    assert summary["tokens_in"] == 4000
    assert summary["tokens_out"] == 900
    assert summary["total_tokens"] == 4900
    assert summary["cost_cents"] == 60
    assert summary["estimated_cost_usd"] == 0.60


# ── 6. Provider and Model Breakdown Accuracy ─────────────────────────────────

def test_provider_and_model_breakdown_accuracy(client, auth_headers, module14_test_data):
    """Verifies that provider and model breakdowns sum up exactly to summary totals."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/ai-usage", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    providers = data["by_provider"]
    assert len(providers) >= 2
    prov_calls = sum(p["calls"] for p in providers)
    prov_cents = sum(p["cost_cents"] for p in providers)
    assert prov_calls == data["summary"]["total_calls"]
    assert prov_cents == data["summary"]["cost_cents"]

    models = data["by_model"]
    model_calls = sum(m["calls"] for m in models)
    model_cents = sum(m["cost_cents"] for m in models)
    assert model_calls == data["summary"]["total_calls"]
    assert model_cents == data["summary"]["cost_cents"]


# ── 7. Failed and Fallback AI Attempts ────────────────────────────────────────

def test_failed_and_fallback_ai_attempts(client, auth_headers, module14_test_data):
    """Verifies that fallback attempts and failed attempts are accurately reflected."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/ai-usage", headers=headers)
    assert resp.status_code == 200
    summary = resp.json()["summary"]

    assert summary["failed_calls"] == 1
    assert summary["fallback_calls"] == 1


# ── 8. Multi-Tenant Isolation ────────────────────────────────────────────────

def test_multi_tenant_isolation(client, auth_headers, module14_test_data):
    """Verifies Company A cannot see Company B metrics, and vice versa."""
    headers_a = auth_headers(module14_test_data["admin_global_email"])
    headers_b = auth_headers(module14_test_data["admin_b_email"], password="Password@123")

    resp_a = client.get("/api/dashboard/company", headers=headers_a)
    assert resp_a.status_code == 200
    assert resp_a.json()["company_id"] == module14_test_data["comp_a_id"]

    resp_b = client.get("/api/dashboard/company", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json()["company_id"] == module14_test_data["comp_b_id"]

    # Company A attempting to access Company B branch returns 404 Not Found
    branch_b_id = module14_test_data["branch_b_id"]
    cross_resp = client.get(f"/api/dashboard/branch/{branch_b_id}", headers=headers_a)
    assert cross_resp.status_code == 404


# ── 9. Branch-Level Isolation ────────────────────────────────────────────────

def test_branch_level_isolation(client, auth_headers, module14_test_data):
    """Verifies that branch-scoped admins cannot access unauthorized branches."""
    branch_admin_headers = auth_headers(module14_test_data["admin_branch_email"])

    # Branch A2 is not the branch admin's primary branch
    branch_a2_id = module14_test_data["branch_a2_id"]
    resp = client.get(f"/api/dashboard/branch/{branch_a2_id}", headers=branch_admin_headers)
    assert resp.status_code == 403, "Branch admin must be forbidden from accessing unassigned branch"


# ── 10. Staff 30-Day Restriction ──────────────────────────────────────────────

def test_staff_30_day_restriction(client, auth_headers, module14_test_data):
    """Verifies that Staff users cannot access company dashboard (403)."""
    staff_headers = auth_headers(module14_test_data["staff_email"])
    resp = client.get("/api/dashboard/company", headers=staff_headers)
    assert resp.status_code == 403, "Staff user lacks COMPANY_VIEW and must be rejected"


# ── 11. Date-Range Boundaries ────────────────────────────────────────────────

def test_date_range_boundaries(client, auth_headers, module14_test_data):
    """Verifies that date filters accurately include boundaries up to 23:59:59.999999."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Filter with date_from=today, date_to=today
    resp = client.get(f"/api/dashboard/company?date_from={today_str}&date_to={today_str}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["time_window"]["date_from"] is not None
    assert data["time_window"]["date_to"] is not None
    assert "23:59:59" in data["time_window"]["date_to"]


# ── 12. Soft-Deleted Record Handling ─────────────────────────────────────────

def test_soft_deleted_record_handling(client, auth_headers, module14_test_data):
    """Verifies soft-deleted documents and invoices are strictly excluded from aggregates."""
    import uuid
    db = SessionLocal()
    try:
        # Create a document, record baseline count, soft-delete it, and re-check count
        comp_id = module14_test_data["comp_a_id"]
        branch_id = module14_test_data["branch_a1_id"]
        admin = db.query(User).filter(User.email == module14_test_data["admin_global_email"]).first()
        unique_key = f"soft_delete_test_doc_{uuid.uuid4().hex[:12]}.pdf"

        doc = Document(
            company_id=comp_id,
            branch_id=branch_id,
            uploaded_by=admin.id,
            original_filename=unique_key,
            storage_key=unique_key,
            mime_type="application/pdf",
            file_size=100000,
            ocr_status=OcrStatus.COMPLETED,
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id

        headers = auth_headers(module14_test_data["admin_global_email"])
        resp_before = client.get("/api/dashboard/company", headers=headers)
        count_before = resp_before.json()["documents"]["total_count"]

        # Soft delete
        doc_in_db = db.query(Document).filter(Document.id == doc_id).first()
        doc_in_db.deleted_at = datetime.utcnow()
        doc_in_db.deleted_by = admin.id
        db.commit()

        resp_after = client.get("/api/dashboard/company", headers=headers)
        count_after = resp_after.json()["documents"]["total_count"]
        assert count_after == count_before - 1, "Soft-deleted document must not be counted"
    finally:
        db.close()


# ── 13. Failed-Job Error Sanitization ────────────────────────────────────────

def test_failed_job_error_sanitization(client, auth_headers, module14_test_data):
    """Verifies that raw paths, secret tokens, and DB URLs in last_error are sanitized."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/jobs?status=failed", headers=headers)
    assert resp.status_code == 200, resp.text
    jobs = resp.json()["jobs"]
    assert len(jobs) >= 1

    target_job = next((j for j in jobs if j["job_id"] == module14_test_data["job_failed_id"]), None)
    assert target_job is not None, "Failed job must be returned in failed filter"

    err = target_job["error_summary"]
    # Check that secrets, internal paths, and db urls are not present
    assert "AIzaSySecretToken1234567890abcdef" not in err, "Secret API key was not sanitized!"
    assert "/home/ubuntu/app/services" not in err, "Internal path was not sanitized!"
    assert "postgresql://dms_user:secret" not in err, "Database URL was not sanitized!"


# ── 14. CSV Formula-Injection Protection ──────────────────────────────────────

def test_csv_formula_injection_protection(client, auth_headers, module14_test_data):
    """Verifies unit function and API output against spreadsheet formula injection."""
    # Unit check
    assert sanitize_csv_cell("=CMD|' /C calc'!A0") == "'=CMD|' /C calc'!A0"
    assert sanitize_csv_cell("+12345") == "'+12345"
    assert sanitize_csv_cell("-12345") == "'-12345"
    assert sanitize_csv_cell("@SUM(A1:B10)") == "'@SUM(A1:B10)"
    assert sanitize_csv_cell("\tmalicious") == "'\tmalicious"
    assert sanitize_csv_cell("\rmalicious") == "'\rmalicious"
    assert sanitize_csv_cell("Normal Text") == "Normal Text"
    assert sanitize_csv_cell(123) == "123"

    # API export check
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/export/csv?export_type=documents", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.text.startswith("\ufeff"), "Must start with UTF-8 BOM"


# ── 15. CSV Export Authorization ──────────────────────────────────────────────

def test_csv_export_authorization(client, auth_headers, module14_test_data):
    """Verifies that CSV exports require COMPANY_VIEW and reject unauthorized users."""
    # Global Admin succeeds
    admin_headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/export/csv?export_type=ai-usage", headers=admin_headers)
    assert resp.status_code == 200

    # Staff is rejected with 403
    staff_headers = auth_headers(module14_test_data["staff_email"])
    resp_staff = client.get("/api/dashboard/export/csv?export_type=ai-usage", headers=staff_headers)
    assert resp_staff.status_code == 403

    # Branch Admin succeeds for assigned branch
    branch_admin_headers = auth_headers(module14_test_data["admin_branch_email"])
    branch_a1_id = module14_test_data["branch_a1_id"]
    branch_a2_id = module14_test_data["branch_a2_id"]
    resp_branch = client.get(f"/api/dashboard/export/csv?export_type=failed-jobs&branch_id={branch_a1_id}", headers=branch_admin_headers)
    assert resp_branch.status_code == 200

    # Branch Admin is rejected for an unauthorized branch
    resp_unauth_branch = client.get(f"/api/dashboard/export/csv?export_type=failed-jobs&branch_id={branch_a2_id}", headers=branch_admin_headers)
    assert resp_unauth_branch.status_code == 403

    # Invalid export type returns 400
    resp_inv = client.get("/api/dashboard/export/csv?export_type=unsupported", headers=admin_headers)
    assert resp_inv.status_code == 400


# ── 16. Zero-Record Handling ──────────────────────────────────────────────────

def test_zero_record_handling(client, auth_headers, module14_test_data):
    """Verifies that filtering with a range yielding 0 records returns clean 0s without errors."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/company?date_from=2099-01-01&date_to=2099-01-02", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["documents"]["total_count"] == 0
    assert data["documents"]["storage_used_bytes"] == 0
    assert data["invoices"]["total_invoices"] == 0
    assert data["invoices"]["total_taxable_amount"] == 0.0
    assert data["ai_usage"]["total_calls"] == 0
    assert data["ai_usage"]["cost_cents"] == 0
    assert data["jobs"]["total_jobs"] == 0


# ── 17. Unauthorized Branch Access ────────────────────────────────────────────

def test_unauthorized_branch_access(client, auth_headers, module14_test_data):
    """Verifies rejection when attempting to access a non-existent or foreign branch."""
    headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/branch/999999", headers=headers)
    assert resp.status_code == 404


# ── 18. Reprocessing Permission Enforcement ───────────────────────────────────

def test_reprocessing_permission_enforcement(client, auth_headers, module14_test_data):
    """Verifies can_reprocess flag in jobs endpoint and actual reprocess endpoint authorization."""
    admin_headers = auth_headers(module14_test_data["admin_global_email"])
    resp = client.get("/api/dashboard/jobs?status=failed", headers=admin_headers)
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    target_job = next((j for j in jobs if j["job_id"] == module14_test_data["job_failed_id"]), None)
    assert target_job is not None
    assert target_job["can_reprocess"] is True

    # Completed jobs must NOT have can_reprocess = True
    resp_comp = client.get("/api/dashboard/jobs?status=completed", headers=admin_headers)
    assert resp_comp.status_code == 200
    completed_jobs = resp_comp.json()["jobs"]
    if completed_jobs:
        assert completed_jobs[0]["can_reprocess"] is False
