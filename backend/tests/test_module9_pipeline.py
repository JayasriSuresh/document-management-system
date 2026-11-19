"""
Module 9 Test Suite — Document Pipeline Hardening and Durable Job Queue.

Covers:
1. Binary magic byte & structural file validation (FileValidator)
2. Storage adapter path traversal & isolation guards
3. Durable PostgreSQL Job Queue (JobQueueService, SKIP LOCKED, lease recovery, backoff)
4. SHA-256 duplicate detection & anti-enumeration (same company 409, cross-company 200)
5. Soft-delete and authenticated restore lifecycle (missing file check, duplicate conflict check)
6. Multi-file batch upload API (partial success, status summaries)
7. Authenticated file serving with secure headers (nosniff, private no-store)
8. Server-side pagination and filtering
"""

import io
import time
from datetime import datetime, timedelta
import pytest
from PIL import Image

from app.models import Company, Branch, User, UserRole, UserRoleAssignment, Document, ProcessingJob, OcrStatus
from app.auth import get_password_hash
from app.services.file_validator import (
    FileValidator,
    ERR_UNSUPPORTED_TYPE,
    ERR_CONTENT_MISMATCH,
    ERR_MALFORMED_PDF,
    ERR_PDF_PAGE_COUNT,
    ERR_IMAGE_DIMENSIONS,
    ERR_DECOMPRESSION_BOMB,
)
from app.services.job_queue import JobQueueService, ActiveJobConflictError
from app.storage import get_storage_adapter
from app.config import settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pdf_bytes(page_count: int = 1) -> bytes:
    """Generate minimal valid PDF bytes with N pages."""
    kids = " ".join([f"{i+3} 0 R" for i in range(page_count)])
    header = (
        "%PDF-1.4\n"
        "1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        f"2 0 obj <</Type /Pages /Kids [{kids}] /Count {page_count}>> endobj\n"
    ).encode("utf-8")
    pages = []
    for i in range(page_count):
        pages.append(f"{i+3} 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>> endobj\n".encode("utf-8"))
    
    xref_pos = len(header) + sum(len(p) for p in pages)
    trailer = (
        f"xref\n0 {page_count + 3}\n0000000000 65535 f \n"
        f"trailer <</Size {page_count + 3} /Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("utf-8")
    return header + b"".join(pages) + trailer


def _make_jpeg_bytes(w: int = 64, h: int = 64, color: tuple = (200, 50, 50)) -> bytes:
    im = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_bytes(w: int = 64, h: int = 64, color: tuple = (50, 200, 50)) -> bytes:
    im = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ── Isolated Test Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def pipe_tenants(db):
    """
    Creates 2 isolated test companies with branches and admin users for Module 9 tests.
    Guarantees strict cleanup in teardown without leaving fixture artifacts.
    """
    c1 = Company(name="Pipeline Test Alpha", code=f"PIPE_A_{int(time.time()*1000)%100000}")
    c2 = Company(name="Pipeline Test Beta", code=f"PIPE_B_{int(time.time()*1000)%100000}")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    b1_a = Branch(company_id=c1.id, name="Alpha Branch 1", code="AL1")
    b1_b = Branch(company_id=c1.id, name="Alpha Branch 2", code="AL2")
    b2_a = Branch(company_id=c2.id, name="Beta Branch 1", code="BE1")
    db.add_all([b1_a, b1_b, b2_a])
    db.commit()
    db.refresh(b1_a)
    db.refresh(b1_b)
    db.refresh(b2_a)

    pwd = get_password_hash("PipelinePass@123")
    u1 = User(company_id=c1.id, branch_id=b1_a.id, name="Admin Alpha1", email=f"admin_a1_{c1.id}@example.com", password_hash=pwd, role=UserRole.ADMIN)
    u2 = User(company_id=c1.id, branch_id=b1_b.id, name="Admin Alpha2", email=f"admin_a2_{c1.id}@example.com", password_hash=pwd, role=UserRole.ADMIN)
    u3 = User(company_id=c2.id, branch_id=b2_a.id, name="Admin Beta1", email=f"admin_b1_{c2.id}@example.com", password_hash=pwd, role=UserRole.ADMIN)
    db.add_all([u1, u2, u3])
    db.commit()
    db.refresh(u1)
    db.refresh(u2)
    db.refresh(u3)

    # Grant GLOBAL_ADMIN company role assignments
    db.add_all([
        UserRoleAssignment(user_id=u1.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=c1.id),
        UserRoleAssignment(user_id=u2.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=c1.id),
        UserRoleAssignment(user_id=u3.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=c2.id),
    ])
    db.commit()

    fixture_data = {
        "c1": c1, "c2": c2,
        "b1_a": b1_a, "b1_b": b1_b, "b2_a": b2_a,
        "u1": u1, "u2": u2, "u3": u3,
        "password": "PipelinePass@123",
    }
    yield fixture_data

    # Teardown
    try:
        db.query(ProcessingJob).filter(ProcessingJob.company_id.in_([c1.id, c2.id])).delete(synchronize_session=False)
        db.query(Document).filter(Document.company_id.in_([c1.id, c2.id])).delete(synchronize_session=False)
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_([u1.id, u2.id, u3.id])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([u1.id, u2.id, u3.id])).delete(synchronize_session=False)
        db.query(Branch).filter(Branch.id.in_([b1_a.id, b1_b.id, b2_a.id])).delete(synchronize_session=False)
        db.query(Company).filter(Company.id.in_([c1.id, c2.id])).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


# ── 1. Binary Magic Byte & Structural Validation Tests ────────────────────────

def test_file_validator_valid_pdf():
    pdf_bytes = _make_pdf_bytes(page_count=2)
    res = FileValidator.validate("test_doc.pdf", pdf_bytes)
    assert res.is_valid is True
    assert res.mime_type == "application/pdf"
    assert res.page_count == 2
    assert len(res.sha256) == 64


def test_file_validator_valid_jpeg():
    jpeg_bytes = _make_jpeg_bytes(100, 80)
    res = FileValidator.validate("photo.jpg", jpeg_bytes)
    assert res.is_valid is True
    assert res.mime_type == "image/jpeg"
    assert res.width == 100
    assert res.height == 80


def test_file_validator_valid_png():
    png_bytes = _make_png_bytes(50, 50)
    res = FileValidator.validate("graphic.png", png_bytes)
    assert res.is_valid is True
    assert res.mime_type == "image/png"
    assert res.width == 50
    assert res.height == 50


def test_file_validator_renamed_executable_rejected():
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100
    res = FileValidator.validate("legit_invoice.pdf", fake_exe)
    assert res.is_valid is False
    assert res.error_code == ERR_UNSUPPORTED_TYPE


def test_file_validator_mismatched_extension_rejected():
    jpeg_bytes = _make_jpeg_bytes()
    # JPEG bytes with .png extension
    res = FileValidator.validate("spoofed.png", jpeg_bytes)
    assert res.is_valid is False
    assert res.error_code == ERR_CONTENT_MISMATCH


def test_file_validator_malformed_pdf_rejected():
    # Has %PDF- signature but corrupted trailer/structure
    corrupt_pdf = b"%PDF-1.4\ncorrupted garbage without valid objects or xref"
    res = FileValidator.validate("bad.pdf", corrupt_pdf)
    assert res.is_valid is False
    assert res.error_code == ERR_MALFORMED_PDF


def test_file_validator_pdf_page_limit_enforced(monkeypatch):
    monkeypatch.setattr(settings, "MAX_PDF_PAGES", 1)
    two_page_pdf = _make_pdf_bytes(page_count=2)
    res = FileValidator.validate("multipage.pdf", two_page_pdf)
    assert res.is_valid is False
    assert res.error_code == ERR_PDF_PAGE_COUNT


def test_file_validator_image_dimension_limit_enforced(monkeypatch):
    monkeypatch.setattr(settings, "MAX_IMAGE_WIDTH", 50)
    oversized_jpeg = _make_jpeg_bytes(w=60, h=40)
    res = FileValidator.validate("big.jpg", oversized_jpeg)
    assert res.is_valid is False
    assert res.error_code == ERR_IMAGE_DIMENSIONS


# ── 2. Storage Adapter Security & Path Traversal Guards ───────────────────────

def test_storage_adapter_rejects_path_traversal():
    from fastapi import HTTPException
    storage = get_storage_adapter()
    with pytest.raises((ValueError, RuntimeError, HTTPException)):
        storage.save("../../etc/shadow", b"evil")


# ── 3. Durable Job Queue & Worker Lease Tests ─────────────────────────────────

def test_job_queue_enqueue_and_claim(db, pipe_tenants):
    c1 = pipe_tenants["c1"]
    b1_a = pipe_tenants["b1_a"]
    u1 = pipe_tenants["u1"]

    # Create dummy doc
    doc = Document(
        company_id=c1.id,
        branch_id=b1_a.id,
        uploaded_by=u1.id,
        original_filename="queue_test.pdf",
        storage_key="c1/b1/documents/queue_test_uuid/orig.pdf",
        mime_type="application/pdf",
        file_size=100,
        ocr_status=OcrStatus.UPLOADED,
    )
    db.add(doc)
    db.commit()

    # Enqueue
    job = JobQueueService.enqueue_job(db, document_id=doc.id, company_id=c1.id, branch_id=b1_a.id)
    assert job.status == "pending"
    assert job.attempts == 0

    # Claim
    worker_1 = "test-worker-1"
    claimed = JobQueueService.claim_next_job(db, worker_id=worker_1)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "running"
    assert claimed.locked_by == worker_1
    assert claimed.attempts == 1

    # Second claim should find no pending jobs
    worker_2 = "test-worker-2"
    second_claim = JobQueueService.claim_next_job(db, worker_id=worker_2)
    assert second_claim is None

    # Complete job
    completed = JobQueueService.complete_job(db, job_id=job.id, worker_id=worker_1)
    assert completed is True
    db.refresh(job)
    assert job.status == "completed"
    assert job.locked_by is None


def test_job_queue_stale_lock_recovery(db, pipe_tenants):
    c1 = pipe_tenants["c1"]
    b1_a = pipe_tenants["b1_a"]
    u1 = pipe_tenants["u1"]

    doc = Document(
        company_id=c1.id,
        branch_id=b1_a.id,
        uploaded_by=u1.id,
        original_filename="stale_test.pdf",
        storage_key="c1/b1/documents/stale_test_uuid/orig.pdf",
        mime_type="application/pdf",
        file_size=100,
        ocr_status=OcrStatus.UPLOADED,
    )
    db.add(doc)
    db.commit()

    job = JobQueueService.enqueue_job(db, document_id=doc.id, company_id=c1.id, branch_id=b1_a.id)
    # Simulate a crashed worker whose lock was acquired 400 seconds ago
    job.status = "running"
    job.locked_by = "dead-worker"
    job.locked_at = datetime.utcnow() - timedelta(seconds=400)
    job.attempts = 1
    db.commit()

    # Next claim should detect stale lock and reclaim it
    new_worker = "healthy-worker"
    reclaimed = JobQueueService.claim_next_job(db, worker_id=new_worker, lock_timeout_seconds=300)
    assert reclaimed is not None
    assert reclaimed.id == job.id
    assert reclaimed.locked_by == new_worker
    assert reclaimed.status == "running"


def test_job_queue_fail_and_exponential_backoff(db, pipe_tenants):
    c1 = pipe_tenants["c1"]
    b1_a = pipe_tenants["b1_a"]
    u1 = pipe_tenants["u1"]

    doc = Document(
        company_id=c1.id,
        branch_id=b1_a.id,
        uploaded_by=u1.id,
        original_filename="fail_test.pdf",
        storage_key="c1/b1/documents/fail_test_uuid/orig.pdf",
        mime_type="application/pdf",
        file_size=100,
        ocr_status=OcrStatus.UPLOADED,
    )
    db.add(doc)
    db.commit()

    job = JobQueueService.enqueue_job(db, document_id=doc.id, company_id=c1.id, branch_id=b1_a.id)
    worker = "fail-worker"
    JobQueueService.claim_next_job(db, worker_id=worker)

    # Fail job on attempt 1 (retryable)
    JobQueueService.fail_job(db, job_id=job.id, worker_id=worker, error_message="Network glitch", is_retryable=True)
    db.refresh(job)
    assert job.status == "pending"
    assert job.run_after > datetime.utcnow()
    assert "Network glitch" in job.last_error

    # Simulate retry claim and exhaust max attempts
    job.status = "running"
    job.locked_by = worker
    job.attempts = job.max_attempts
    db.commit()
    JobQueueService.fail_job(db, job_id=job.id, worker_id=worker, error_message="Permanent failure", is_retryable=True)
    db.refresh(job)
    assert job.status == "failed"
    assert job.completed_at is not None


def test_job_queue_lease_verification_prevents_stale_overwrite(db, pipe_tenants):
    c1 = pipe_tenants["c1"]
    b1_a = pipe_tenants["b1_a"]
    u1 = pipe_tenants["u1"]

    doc = Document(
        company_id=c1.id,
        branch_id=b1_a.id,
        uploaded_by=u1.id,
        original_filename="lease_test.pdf",
        storage_key="c1/b1/documents/lease_test_uuid/orig.pdf",
        mime_type="application/pdf",
        file_size=100,
        ocr_status=OcrStatus.UPLOADED,
    )
    db.add(doc)
    db.commit()

    job = JobQueueService.enqueue_job(db, document_id=doc.id, company_id=c1.id, branch_id=b1_a.id)
    job.status = "running"
    job.locked_by = "active-worker-2"
    db.commit()

    # Stale worker 1 attempts to complete
    success = JobQueueService.complete_job(db, job_id=job.id, worker_id="stale-worker-1")
    assert success is False
    db.refresh(job)
    assert job.status == "running"  # Unchanged


# ── 4. Duplicate Detection & Anti-Enumeration Tests ───────────────────────────

def test_upload_duplicate_detection_same_company(client, pipe_tenants):
    u1 = pipe_tenants["u1"]
    pwd = pipe_tenants["password"]

    login_resp = client.post("/api/auth/login", json={"email": u1.email, "password": pwd})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    jpeg_bytes = _make_jpeg_bytes(80, 80, color=(12, 34, 56))

    # 1. First upload succeeds
    r1 = client.post("/api/documents", headers=headers, files={"file": ("orig.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")})
    assert r1.status_code == 200
    doc1 = r1.json()

    # 2. Second upload with same bytes in same company returns 409 Conflict
    r2 = client.post("/api/documents", headers=headers, files={"file": ("duplicate.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")})
    assert r2.status_code == 409
    assert "duplicate" in r2.json()["detail"].lower()


def test_upload_duplicate_cross_branch_same_company_anti_enumeration(client, pipe_tenants):
    u1 = pipe_tenants["u1"]  # Branch 1
    u2 = pipe_tenants["u2"]  # Branch 2 of SAME company
    pwd = pipe_tenants["password"]

    t1 = client.post("/api/auth/login", json={"email": u1.email, "password": pwd}).json()["access_token"]
    t2 = client.post("/api/auth/login", json={"email": u2.email, "password": pwd}).json()["access_token"]

    jpeg_bytes = _make_jpeg_bytes(80, 80, color=(78, 90, 12))

    # Upload in Branch 1
    r1 = client.post("/api/documents", headers={"Authorization": f"Bearer {t1}"}, files={"file": ("b1.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")})
    assert r1.status_code == 200

    # Upload in Branch 2 of SAME company -> 409 without leaking Branch 1 ID
    r2 = client.post("/api/documents", headers={"Authorization": f"Bearer {t2}"}, files={"file": ("b2.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")})
    assert r2.status_code == 409
    # Must NOT reveal the other branch's ID in the error detail
    assert "branch" not in r2.json()["detail"].lower()


def test_upload_identical_file_cross_company_isolation(client, pipe_tenants):
    u1 = pipe_tenants["u1"]  # Company 1
    u3 = pipe_tenants["u3"]  # Company 2
    pwd = pipe_tenants["password"]

    t1 = client.post("/api/auth/login", json={"email": u1.email, "password": pwd}).json()["access_token"]
    t3 = client.post("/api/auth/login", json={"email": u3.email, "password": pwd}).json()["access_token"]

    png_bytes = _make_png_bytes(64, 64, color=(100, 150, 200))

    # Upload in Company 1
    r1 = client.post("/api/documents", headers={"Authorization": f"Bearer {t1}"}, files={"file": ("c1.png", io.BytesIO(png_bytes), "image/png")})
    assert r1.status_code == 200

    # Upload identical file in Company 2 -> Allowed! (Tenant Isolation)
    r2 = client.post("/api/documents", headers={"Authorization": f"Bearer {t3}"}, files={"file": ("c2.png", io.BytesIO(png_bytes), "image/png")})
    assert r2.status_code == 200
    assert r1.json()["sha256"] == r2.json()["sha256"]
    assert r1.json()["company_id"] != r2.json()["company_id"]


# ── 5. Soft Delete and Restore Lifecycle Tests ────────────────────────────────

def test_soft_delete_and_restore_lifecycle(client, pipe_tenants):
    u1 = pipe_tenants["u1"]
    pwd = pipe_tenants["password"]
    token = client.post("/api/auth/login", json={"email": u1.email, "password": pwd}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    jpeg_bytes = _make_jpeg_bytes(70, 70, color=(111, 222, 111))
    up = client.post("/api/documents", headers=headers, files={"file": ("to_del.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")})
    doc_id = up.json()["id"]

    # 1. Soft delete
    del_resp = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 200

    # 2. Excluded from normal list
    list_resp = client.get("/api/documents", headers=headers)
    doc_ids = [d["id"] for d in list_resp.json()]
    assert doc_id not in doc_ids

    # 3. Included in list with include_deleted=true
    trash_resp = client.get("/api/documents?include_deleted=true", headers=headers)
    trash_ids = [d["id"] for d in trash_resp.json()]
    assert doc_id in trash_ids

    # 4. Restore document
    restore_resp = client.post(f"/api/documents/{doc_id}/restore", headers=headers)
    assert restore_resp.status_code == 200
    assert restore_resp.json()["deleted_at"] is None

    # 5. Back in normal list
    list_again = client.get("/api/documents", headers=headers)
    assert doc_id in [d["id"] for d in list_again.json()]


def test_restore_conflict_when_active_duplicate_exists(client, pipe_tenants):
    u1 = pipe_tenants["u1"]
    pwd = pipe_tenants["password"]
    token = client.post("/api/auth/login", json={"email": u1.email, "password": pwd}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bytes_x = _make_jpeg_bytes(70, 70, color=(55, 66, 77))

    # Upload Doc A
    doc_a = client.post("/api/documents", headers=headers, files={"file": ("doc_a.jpg", io.BytesIO(bytes_x), "image/jpeg")}).json()
    # Delete Doc A
    client.delete(f"/api/documents/{doc_a['id']}", headers=headers)

    # Now that Doc A is deleted, uploading identical Doc B is allowed!
    doc_b = client.post("/api/documents", headers=headers, files={"file": ("doc_b.jpg", io.BytesIO(bytes_x), "image/jpeg")}).json()
    assert doc_b["id"] != doc_a["id"]

    # Attempting to restore Doc A while Doc B is active must return 409 Conflict!
    res_conflict = client.post(f"/api/documents/{doc_a['id']}/restore", headers=headers)
    assert res_conflict.status_code == 409
    assert "active document with identical content" in res_conflict.json()["detail"].lower()


# ── 6. Multi-File Batch Upload API Tests ──────────────────────────────────────

def test_batch_upload_with_partial_results(client, pipe_tenants):
    u1 = pipe_tenants["u1"]
    pwd = pipe_tenants["password"]
    token = client.post("/api/auth/login", json={"email": u1.email, "password": pwd}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    f1 = ("valid1.jpg", _make_jpeg_bytes(50, 50, color=(1, 2, 3)), "image/jpeg")
    f2 = ("bad_script.py", b"print('malicious')", "text/x-python")
    f3 = ("valid2.png", _make_png_bytes(50, 50, color=(4, 5, 6)), "image/png")

    resp = client.post(
        "/api/documents/batch",
        headers=headers,
        files=[
            ("files", f1),
            ("files", f2),
            ("files", f3),
        ],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["successful"] == 2
    assert data["failed"] == 1

    results = {r["filename"]: r for r in data["results"]}
    assert results["valid1.jpg"]["status"] == "success"
    assert results["bad_script.py"]["status"] == "error"
    assert results["bad_script.py"]["error_code"] == ERR_UNSUPPORTED_TYPE
    assert results["valid2.png"]["status"] == "success"


# ── 7. Authenticated File Serving & Security Headers Tests ───────────────────

def test_authenticated_file_serving_security_headers(client, pipe_tenants):
    u1 = pipe_tenants["u1"]
    pwd = pipe_tenants["password"]
    token = client.post("/api/auth/login", json={"email": u1.email, "password": pwd}).json()["access_token"]

    jpeg_bytes = _make_jpeg_bytes(60, 60, color=(99, 88, 77))
    up = client.post(
        "/api/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("secure_test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
    )
    doc_id = up.json()["id"]

    # Serve file with Bearer header
    resp = client.get(f"/api/documents/{doc_id}/file", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert "private" in resp.headers.get("Cache-Control", "")
    assert "no-store" in resp.headers.get("Cache-Control", "")
    assert resp.headers.get("Content-Type") == "image/jpeg"

    # Serve file with query param token
    resp_query = client.get(f"/api/documents/{doc_id}/file?token={token}")
    assert resp_query.status_code == 200
    assert resp_query.headers.get("X-Content-Type-Options") == "nosniff"


# ── 8. Server-Side Pagination & Filtering Tests ───────────────────────────────

def test_server_side_pagination(client, pipe_tenants):
    u1 = pipe_tenants["u1"]
    pwd = pipe_tenants["password"]
    token = client.post("/api/auth/login", json={"email": u1.email, "password": pwd}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload 3 distinct files
    for i in range(3):
        b = _make_jpeg_bytes(50, 50, color=(10 + i, 20 + i, 30 + i))
        client.post("/api/documents", headers=headers, files={"file": (f"page_{i}.jpg", io.BytesIO(b), "image/jpeg")})

    # Page 1 with page_size=2
    r1 = client.get("/api/documents?page=1&page_size=2&paginate=true", headers=headers)
    assert r1.status_code == 200
    p1 = r1.json()
    assert p1["page"] == 1
    assert p1["page_size"] == 2
    assert len(p1["items"]) == 2
    assert p1["total"] >= 3
    assert p1["total_pages"] >= 2

    # Page 2 with page_size=2
    r2 = client.get("/api/documents?page=2&page_size=2&paginate=true", headers=headers)
    assert r2.status_code == 200
    p2 = r2.json()
    assert p2["page"] == 2
    assert len(p2["items"]) >= 1

    # Verify no overlapping items between pages
    page1_ids = {item["id"] for item in p1["items"]}
    page2_ids = {item["id"] for item in p2["items"]}
    assert len(page1_ids.intersection(page2_ids)) == 0
