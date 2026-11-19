"""
Tests for /api/invoices endpoints: listing, RBAC, and search.
"""

import pytest
from app.models import Invoice


def test_invoices_requires_auth(client):
    resp = client.get("/api/invoices")
    assert resp.status_code == 401


def test_invoices_listing_tenant_isolation(client, auth_headers):
    samrethi_headers = auth_headers("samrethi@example.com")
    resp = client.get("/api/invoices", headers=samrethi_headers)
    assert resp.status_code == 200
    invoices = resp.json()
    assert isinstance(invoices, list)
    for inv in invoices:
        assert inv["tenant_name"] in ("Chennai", "Unknown")


def test_invoices_search(client, auth_headers):
    jayasri_headers = auth_headers("jayasri@example.com")
    resp = client.get("/api/invoices?search=INV", headers=jayasri_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_invoices_kind_and_status_filtering(client, auth_headers):
    jayasri_headers = auth_headers("jayasri@example.com")
    
    # Filter by kind=copy
    resp_copy = client.get("/api/invoices?kind=copy", headers=jayasri_headers)
    assert resp_copy.status_code == 200
    for inv in resp_copy.json():
        assert inv["kind"] == "copy"

    # Filter by kind=generated
    resp_gen = client.get("/api/invoices?kind=generated", headers=jayasri_headers)
    assert resp_gen.status_code == 200
    for inv in resp_gen.json():
        assert inv["kind"] == "generated"

    # Filter by status
    resp_stat = client.get("/api/invoices?status=available", headers=jayasri_headers)
    assert resp_stat.status_code == 200
    for inv in resp_stat.json():
        assert inv["status"] == "available"


def test_invoices_stats_endpoint(client, auth_headers):
    jayasri_headers = auth_headers("jayasri@example.com")
    resp = client.get("/api/invoices/stats", headers=jayasri_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_count" in data
    assert "copies_count" in data
    assert "sales_count" in data
    assert "total_billed_value" in data
    assert isinstance(data["total_count"], int)
