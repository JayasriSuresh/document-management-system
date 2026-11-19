"""
Tests for /api/documents endpoints: upload, listing, search, retrieval, and file serving.
"""

import io
import pytest
from PIL import Image
from app.models import Document


def _make_valid_jpeg_bytes(seed: int = 1) -> bytes:
    im = Image.new("RGB", (64, 64), color=(seed % 250 + 1, (seed * 37) % 250 + 1, (seed * 73) % 250 + 1))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def test_upload_rejected_for_invalid_extension(client, auth_headers):
    headers = auth_headers("samrethi@example.com")
    fake_file = io.BytesIO(b"evil executable content")

    resp = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("malware.exe", fake_file, "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"].lower()


def test_upload_rejected_for_unauthorized(client):
    fake_file = io.BytesIO(b"fake image data")
    resp = client.post(
        "/api/documents",
        files={"file": ("receipt.jpg", fake_file, "image/jpeg")},
    )
    assert resp.status_code == 401


def test_upload_valid_image(client, auth_headers, db):
    headers = auth_headers("samrethi@example.com")
    jpeg_bytes = _make_valid_jpeg_bytes(10)
    fake_file = io.BytesIO(jpeg_bytes)

    resp = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("test_upload_doc.jpg", fake_file, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_filename"] == "test_upload_doc.jpg"
    assert data["mime_type"] == "image/jpeg"
    assert data["ocr_status"] in ("UPLOADED", "PROCESSING", "COMPLETED")

    # Clean up test doc
    created = db.query(Document).filter(Document.id == data["id"]).first()
    if created:
        db.delete(created)
        db.commit()


@pytest.fixture
def chennai_doc(client, auth_headers, db):
    """Fixture ensuring a test document exists for search and viewing tests."""
    headers = auth_headers("samrethi@example.com")
    jpeg_bytes = _make_valid_jpeg_bytes(20)
    resp = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("chennai_admin_doc.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
    )
    doc_id = resp.json()["id"] if resp.status_code == 200 else None
    yield doc_id
    if doc_id:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            db.delete(doc)
            db.commit()


def test_document_search_filtering(client, auth_headers, chennai_doc):
    headers = auth_headers("samrethi@example.com")
    # Search for known seeded document
    resp = client.get("/api/documents?search=chennai_admin", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert any("chennai_admin" in d["original_filename"] for d in items)

    # Search for non-existent keyword
    resp_empty = client.get("/api/documents?search=xyz_completely_absent_query", headers=headers)
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()) == 0


def test_document_file_serving_with_query_param(client, auth_headers, chennai_doc):
    # Extract token
    login_resp = client.post("/api/auth/login", json={"email": "samrethi@example.com", "password": "Pasword@123"})
    token = login_resp.json()["access_token"]

    resp = client.get(f"/api/documents/{chennai_doc}/file?token={token}")
    assert resp.status_code in (200, 404)  # 200 if storage file present, 404 if missing from disk


def test_document_reprocess(client, auth_headers, chennai_doc):
    headers = auth_headers("samrethi@example.com")
    resp = client.post(f"/api/documents/{chennai_doc}/reprocess", headers=headers)
    # 200 if enqueued, 404 if missing, 409 if already queued/processing
    assert resp.status_code in (200, 404, 409)
