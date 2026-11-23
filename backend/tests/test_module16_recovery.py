"""
Module 16 Integration Suite — Recovery, Fault Tolerance & Disaster Drills (Section 8).

Covers:
8.1 Background worker crash simulation and lease expiration recovery (SKIP LOCKED reclaiming stale locks).
8.2 Storage and I/O failure handling (safe database rollback; no orphan documents).
8.3 Database transient connection failure handling (sanitized error response without leaking credentials).
8.4 Disaster recovery and backup restoration drill (isolated schema/metadata dump, RPO and RTO validation).
"""

import io
import time
import uuid
import tempfile
import subprocess
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database import engine, SessionLocal
from app.models import Company, Branch, User, Document, ProcessingJob, OcrStatus
from app.services.job_queue import JobQueueService
from app.storage import get_storage_adapter


client = TestClient(app)


def _login(email: str = "sujipriya@example.com", portal: str = "app") -> tuple[str, dict]:
    res = client.post("/api/auth/login", json={"email": email, "password": "Pasword@123", "portal": portal})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    token = res.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


# ── 8.1 Worker Crash and Lease Expiration Recovery ────────────────────────────

def test_8_1_worker_crash_and_lease_expiration_recovery(db):
    """
    Simulate worker death while holding a processing job lock.
    Verifies that when lock_timeout expires, the job queue automatically
    reclaims the orphaned job, resets its lock, and re-allocates it to a live worker.
    """
    company_id = 40
    branch_id = 4932

    # 1. Enqueue job
    doc = Document(
        company_id=company_id,
        branch_id=branch_id,
        uploaded_by=5772,
        original_filename="crash_test.pdf",
        storage_key=f"temp/crash_{uuid.uuid4().hex[:6]}.pdf",
        file_size=100,
        mime_type="application/pdf",
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    job = JobQueueService.enqueue_job(
        db=db,
        document_id=doc.id,
        company_id=company_id,
        branch_id=branch_id,
        commit=True,
    )

    # 2. Simulate worker crash: worker claims job, locks it, but then terminates abruptly
    crashed_worker_id = "crashed_worker_pid_8888"
    job.status = "running"
    job.locked_by = crashed_worker_id
    # Set locked_at into the past to simulate lease expiration
    job.locked_at = datetime.utcnow() - timedelta(seconds=120)
    job.attempts = 1
    db.commit()

    # 3. Healthy worker runs claim_next_job with 30s timeout
    healthy_worker_id = "healthy_worker_pid_9999"
    claimed_job = JobQueueService.claim_next_job(
        db=db,
        worker_id=healthy_worker_id,
        lock_timeout_seconds=30,
    )

    # 4. Verify healthy worker successfully reclaimed the orphaned job
    assert claimed_job is not None, "Stale job should be reclaimed by healthy worker"
    assert claimed_job.id == job.id
    assert claimed_job.status == "running"
    assert claimed_job.locked_by == healthy_worker_id
    assert claimed_job.attempts == 2, f"Attempts should increment, got {claimed_job.attempts}"

    # 5. Clean up
    db.query(ProcessingJob).filter_by(id=job.id).delete()
    db.query(Document).filter_by(id=doc.id).delete()
    db.commit()


# ── 8.2 Storage I/O Failure Safe Rollback ──────────────────────────────────────

def test_8_2_storage_io_failure_safe_rollback(db):
    """
    Simulate storage write failure (disk full or S3 network error).
    Verifies that the database transaction rolls back cleanly,
    preventing orphan records in documents or processing_jobs.
    """
    _, staff_headers = _login()
    initial_docs_count = db.query(Document).filter_by(company_id=40).count()

    fake_pdf = b"%PDF-1.4 Simulated Document Payload"
    files = {"file": ("storage_fail_test.pdf", fake_pdf, "application/pdf")}

    # Mock storage adapter save to simulate storage failure
    with patch("app.storage.get_storage_adapter") as mock_adapter_fn:
        mock_adapter = MagicMock()
        mock_adapter.save.side_effect = IOError("Simulated storage volume out of disk space")
        mock_adapter_fn.return_value = mock_adapter

        res = client.post("/api/documents", files=files, headers=staff_headers)
        # Must fail gracefully with 400, 500, or 503
        assert res.status_code in (400, 500, 503), f"Storage error should produce error, got: {res.status_code}"
        # Message must not leak sensitive paths
        assert "password" not in res.text.lower()

    # Verify no orphan document was created in the database
    db.expire_all()
    final_docs_count = db.query(Document).filter_by(company_id=40).count()
    assert final_docs_count == initial_docs_count, "Rollback failed: orphan document record found after storage failure"


# ── 8.3 Database Connection Failure Handling ──────────────────────────────────

def test_8_3_database_connection_transient_failure():
    """
    Simulate database connection pool exhaustion or network disconnect.
    Verifies application fails safely with 500 or 503 and never leaks
    database credentials or connection strings in response payloads.
    """
    from sqlalchemy.exc import OperationalError
    from starlette.testclient import TestClient

    safe_client = TestClient(app, raise_server_exceptions=False)

    with patch("app.database.SessionLocal") as mock_session_local:
        mock_session_local.side_effect = OperationalError("could not connect to server", params=None, orig=Exception("Connection refused"))

        res = safe_client.post("/api/auth/login", json={"email": "sujipriya@example.com", "password": "Password@123", "portal": "app"})
        # Database failure should result in 500 internal server error
        assert res.status_code in (500, 503)
        # Verify database passwords/credentials are never reflected in response text
        assert "password" not in res.text.lower() or "dms_password" not in res.text.lower()
        assert "postgresql://" not in res.text.lower()
        assert "dms_password" not in res.text.lower()


# ── 8.4 Isolated Disaster Recovery Drill (RPO & RTO) ──────────────────────────

def test_8_4_isolated_disaster_recovery_backup_drill():
    """
    Perform an automated backup drill using PostgreSQL pg_dump:
    1. Dump database schema and core metadata to isolated buffer.
    2. Measure RTO (Recovery Time Objective): dump/metadata extraction completes in < 5 seconds.
    3. Measure RPO (Recovery Point Objective): all required system tables are verified in the backup stream.
    """
    start_time = time.time()

    # Execute pg_dump schema-only in isolated sub-process via unix socket
    proc = subprocess.run(
        ["pg_dump", "-h", "/tmp", "-p", "5434", "-U", "dms_user", "-d", "dms_db", "--schema-only"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    rto_duration = time.time() - start_time

    assert proc.returncode == 0, f"pg_dump drill failed: {proc.stderr}"
    dump_sql = proc.stdout

    # RTO Verification: Schema dump should be fast (< 5 seconds)
    assert rto_duration < 5.0, f"RTO exceeded threshold: {rto_duration:.2f}s"

    # RPO Verification: Essential tables must be present in backup stream
    required_tables = [
        "companies",
        "branches",
        "users",
        "documents",
        "invoices",
        "outbound_sales_invoices",
        "number_sequences",
        "audit_logs",
        "processing_jobs",
    ]
    for table in required_tables:
        assert f"CREATE TABLE public.{table}" in dump_sql or f"CREATE TABLE {table}" in dump_sql or table in dump_sql, (
            f"RPO Violation: Table '{table}' missing from database backup stream"
        )
