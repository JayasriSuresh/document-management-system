"""
Module 16 - Operational Metrics, Monitoring, and Telemetry Validation Tests.

Validates:
  1. Thread-safe in-memory metric tracking (requests, latency percentiles, errors).
  2. AI provider token accounting, latency histograms, and failover tracking.
  3. Security event recording (failed logins, MFA challenges, cross-tenant violations).
  4. Middleware auto-instrumentation of inbound HTTP requests.
  5. Dual-export verification: Clean JSON summary (/api/metrics) and Prometheus exposition format (/metrics).
  6. Multi-threaded concurrency safety.
"""

import threading
import time
from starlette.testclient import TestClient

from app.main import app
from app.services.metrics_service import metrics_service

client = TestClient(app)


def setup_function():
    metrics_service.reset()


def test_9_1_http_metrics_auto_collection():
    """Verify middleware automatically records request count, status code, and latency."""
    res1 = client.get("/health")
    assert res1.status_code == 200

    res2 = client.get("/health")
    assert res2.status_code == 200

    res3 = client.get("/api/metrics")
    assert res3.status_code == 200
    data = res3.json()

    assert data["http"]["total_requests"] >= 2
    assert "2xx" in data["http"]["status_breakdown"]
    assert data["http"]["latency_stats"]["count"] >= 2
    assert data["http"]["latency_stats"]["p50"] >= 0.0


def test_9_2_prometheus_exposition_format():
    """Verify /metrics exports valid Prometheus format with HELP, TYPE, and labels."""
    # Seed some metrics
    metrics_service.record_http_request("POST", "/api/documents", 201, 145.2)
    metrics_service.record_http_request("POST", "/api/documents", 400, 22.1)
    metrics_service.record_ai_request("gemini", "gemini-2.0-flash", 1200, 450, 850.0, success=True)
    metrics_service.record_ai_fallback("gemini", "openai", reason="quota_exceeded")
    metrics_service.record_security_event("cross_tenant_attempt")
    metrics_service.record_job_execution("ocr_processing", 320.0, success=True)

    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers.get("content-type", "")
    content = res.text

    # Verify standard Prometheus structure
    assert "# HELP dms_http_requests_total" in content
    assert "# TYPE dms_http_requests_total counter" in content
    assert 'dms_http_requests_total{method="POST",status="201",family="2xx"} 1' in content

    assert "# HELP dms_ai_requests_total" in content
    assert 'dms_ai_requests_total{provider="gemini",model="gemini-2.0-flash",status="success"} 1' in content
    assert 'dms_ai_tokens_total{provider="gemini",type="input"} 1200' in content
    assert 'dms_ai_tokens_total{provider="gemini",type="output"} 450' in content

    assert "# HELP dms_ai_fallbacks_total" in content
    assert 'dms_ai_fallbacks_total{from_provider="gemini",to_provider="openai"} 1' in content

    assert "# HELP dms_security_events_total" in content
    assert 'dms_security_events_total{event_type="cross_tenant_attempt"} 1' in content

    assert "# HELP dms_background_jobs_total" in content
    assert 'dms_background_jobs_total{job_type="ocr_processing",status="success"} 1' in content


def test_9_3_latency_percentile_computation():
    """Verify p50, p90, p95, and p99 percentiles are mathematically accurate."""
    # Insert 100 known values: 1ms to 100ms
    for i in range(1, 101):
        metrics_service.record_http_request("GET", "/test", 200, float(i))

    summary = metrics_service.get_summary()
    lat = summary["http"]["latency_stats"]

    assert lat["count"] == 100
    assert lat["p50"] == 50.0
    assert lat["p90"] == 90.0
    assert lat["p95"] == 95.0
    assert lat["p99"] == 99.0
    assert lat["avg"] == 50.5


def test_9_4_security_event_aggregation():
    """Verify security event tracking captures and aggregates threat metrics."""
    metrics_service.record_security_event("failed_login")
    metrics_service.record_security_event("failed_login")
    metrics_service.record_security_event("failed_login")
    metrics_service.record_security_event("mfa_challenge_failed")
    metrics_service.record_security_event("rate_limit_exceeded")

    summary = metrics_service.get_summary()
    sec = summary["security"]

    assert sec["failed_login"] == 3
    assert sec["mfa_challenge_failed"] == 1
    assert sec["rate_limit_exceeded"] == 1


def test_9_5_concurrent_metrics_recording_safety():
    """Verify thread-safety when dozens of threads record metrics simultaneously."""
    def worker(worker_id: int):
        for i in range(50):
            metrics_service.record_http_request("GET", f"/api/{worker_id}", 200, float(i))
            metrics_service.record_ai_request("gemini", "flash", 10, 5, 50.0)
            metrics_service.record_security_event("failed_login")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    summary = metrics_service.get_summary()
    assert summary["http"]["total_requests"] == 500
    assert summary["security"]["failed_login"] == 500
    assert summary["ai"]["providers"]["gemini"]["requests_total"] == 500
    assert summary["ai"]["providers"]["gemini"]["tokens_input"] == 5000
