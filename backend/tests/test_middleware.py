"""
Tests for Request-ID middleware, error handlers, and health check.
"""

import uuid
import pytest


def test_health_check_returns_ok_and_env(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "env" in data


def test_request_id_generated_automatically(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    # Verify it looks like a valid UUID
    uuid_str = resp.headers["X-Request-ID"]
    parsed = uuid.UUID(uuid_str)
    assert str(parsed) == uuid_str


def test_custom_request_id_echoed_back(client):
    custom_rid = "custom-test-trace-id-12345"
    resp = client.get("/health", headers={"X-Request-ID": custom_rid})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_rid


def test_404_error_response_shape(client):
    resp = client.get("/api/nonexistent-route-xyz")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert body["error"]["status"] == 404
    assert "request_id" in body["error"]
    assert "detail" in body["error"]


def test_405_method_not_allowed_shape(client):
    # /health is GET only
    resp = client.post("/health")
    assert resp.status_code == 405
    body = resp.json()
    assert "error" in body
    assert body["error"]["status"] == 405
    assert "request_id" in body["error"]
