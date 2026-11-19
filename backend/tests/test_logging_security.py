"""
Security Test Suite: Prevent JWT and Sensitive Data Exposure in Application Logs.

Verifies:
  - Redaction of URL query parameters (?token=, &password=, etc.)
  - Redaction of Bearer tokens in headers and strings
  - Redaction of raw JWT strings
  - Redaction of key-value JSON and dictionary credentials
  - Redaction of tracebacks and exceptions
  - Integration with Uvicorn access logging
  - Integration with FastAPI RequestIdMiddleware (dms.access)
  - End-to-end request handling with valid JWT query parameters
"""

import io
import logging
import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.logging_redactor import (
    redact_sensitive_data,
    SensitiveDataFilter,
    RedactingFormatter,
    RedactingUvicornAccessFormatter,
    apply_redaction_filters,
    SENSITIVE_PARAM_NAMES,
)
from app.main import app
from app.services.job_queue import sanitize_error_message


# ── 1. Unit Tests for redact_sensitive_data ─────────────────────────────────

def test_redact_single_query_param_token():
    sample_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    url = f"/api/documents/492/invoice.pdf?token={sample_jwt}"
    redacted = redact_sensitive_data(url)

    assert "eyJ" not in redacted
    assert redacted == "/api/documents/492/invoice.pdf?token=[REDACTED]"


def test_redact_multiple_query_params():
    sample_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    url = f"/api/documents/492/invoice.pdf?token={sample_jwt}&page=2&format=pdf"
    redacted = redact_sensitive_data(url)

    assert "eyJ" not in redacted
    assert redacted == "/api/documents/492/invoice.pdf?token=[REDACTED]&page=2&format=pdf"


def test_redact_trailing_and_mixed_sensitive_params():
    url = "/api/v1/resource?page=1&password=mysecretpassword123&client_secret=xyz789&limit=50"
    redacted = redact_sensitive_data(url)

    assert "mysecretpassword123" not in redacted
    assert "xyz789" not in redacted
    assert redacted == "/api/v1/resource?page=1&password=[REDACTED]&client_secret=[REDACTED]&limit=50"


def test_redact_bearer_token():
    header = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    redacted = redact_sensitive_data(header)

    assert "eyJ" not in redacted
    assert redacted == "Authorization: Bearer [REDACTED]"


def test_redact_standalone_jwt():
    raw_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    text = f"An unexpected token occurred: {raw_jwt} during validation."
    redacted = redact_sensitive_data(text)

    assert "eyJ" not in redacted
    assert redacted == "An unexpected token occurred: [REDACTED_JWT] during validation."


def test_redact_json_and_dictionary_keys():
    json_str = '{"user": "alice", "password": "SuperSecretPassword!", "token": "tok_12345", "role": "admin"}'
    redacted = redact_sensitive_data(json_str)

    assert "SuperSecretPassword!" not in redacted
    assert "tok_12345" not in redacted
    assert '"password": "[REDACTED]"' in redacted
    assert '"token": "[REDACTED]"' in redacted
    assert '"user": "alice"' in redacted


def test_redact_recursive_data_structures():
    data = {
        "url": "/api/test?token=secret_token&tab=all",
        "nested": [
            "Authorization: Bearer test_bearer_token",
            {"api_key": "sk-1234567890", "count": 42},
        ],
    }
    redacted = redact_sensitive_data(data)

    assert redacted["url"] == "/api/test?token=[REDACTED]&tab=all"
    assert redacted["nested"][0] == "Authorization: Bearer [REDACTED]"
    assert redacted["nested"][1]["api_key"] == "[REDACTED]"
    assert redacted["nested"][1]["count"] == 42


def test_clean_urls_remain_unmodified():
    url = "/api/documents?page=1&limit=20&status=COMPLETED&branch_id=5"
    redacted = redact_sensitive_data(url)
    assert redacted == url


# ── 2. SensitiveDataFilter & RedactingFormatter Tests ───────────────────────

def test_sensitive_data_filter_preserves_format_specifiers():
    """Verify %s format specifiers in record.msg are not destroyed when record.args are present."""
    sample_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connecting to %s with token=%s and status=%d",
        args=("https://api.internal", sample_jwt, 200),
        exc_info=None,
    )
    flt = SensitiveDataFilter()
    assert flt.filter(record) is True

    # Args are redacted
    assert record.args == ("https://api.internal", "[REDACTED_JWT]", 200)
    # Format message works smoothly without TypeError
    formatted = record.getMessage()
    assert formatted == "Connecting to https://api.internal with token=[REDACTED_JWT] and status=200"


def test_sensitive_data_filter_redacts_exc_info():
    """Verify tracebacks are redacted by SensitiveDataFilter before formatting."""
    flt = SensitiveDataFilter()
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    try:
        raise ValueError(f"Connection failed to https://auth.corp?token={token}")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="test.err",
            level=logging.ERROR,
            pathname="test.py",
            lineno=20,
            msg="Exception caught",
            args=(),
            exc_info=sys.exc_info(),
        )

    flt.filter(record)
    assert record.exc_text is not None
    assert "eyJ" not in record.exc_text
    assert "token=[REDACTED]" in record.exc_text


# ── 3. Uvicorn Access Logger Integration Test ───────────────────────────────

def test_uvicorn_access_log_redaction():
    """Simulate Uvicorn's exact logging mechanism and verify token is redacted."""
    stream = io.StringIO()
    uvicorn_access = logging.getLogger("test_uvicorn_access")
    uvicorn_access.setLevel(logging.INFO)
    uvicorn_access.propagate = False

    handler = logging.StreamHandler(stream)
    formatter = RedactingUvicornAccessFormatter(
        '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        use_colors=False,
    )
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())
    uvicorn_access.addHandler(handler)

    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    path = f"/api/documents/492/invoice.pdf?token={token}"

    # Uvicorn emits (client_addr, method, full_path, http_version, status_code)
    uvicorn_access.info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:45322",
        "GET",
        path,
        "1.1",
        200,
    )

    output = stream.getvalue()
    assert "eyJ" not in output
    assert 'GET /api/documents/492/invoice.pdf?token=[REDACTED] HTTP/1.1" 200' in output


# ── 4. Job Queue Error Sanitization ─────────────────────────────────────────

def test_job_queue_error_sanitization():
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123456_def"
    raw_error = f"Failed to download doc: https://storage.corp/file?token={token} from postgresql://user:pass@db:5432/dms"
    sanitized = sanitize_error_message(raw_error)

    assert "eyJ" not in sanitized
    assert "token=[REDACTED]" in sanitized
    assert "postgresql://user:pass" not in sanitized


# ── 5. End-to-End TestClient Request with Token Query Parameter ─────────────

def test_request_with_query_token_is_redacted_in_logs(client: TestClient):
    """
    Perform a live HTTP request with ?token=... to FastAPI TestClient.
    Verify:
      1. Log stream never leaks the token.
      2. The request is processed normally by the application.
    """
    stream = io.StringIO()
    capture_handler = logging.StreamHandler(stream)
    capture_handler.setFormatter(RedactingFormatter("%(levelname)s | %(name)s | %(message)s"))
    capture_handler.addFilter(SensitiveDataFilter())

    root_logger = logging.getLogger()
    dms_access = logging.getLogger("dms.access")
    root_logger.addHandler(capture_handler)
    dms_access.addHandler(capture_handler)

    try:
        # Generate valid token
        valid_token = create_access_token(data={"sub": "1", "company_id": 24, "role": "COMPANY_ADMIN"})

        # Make GET request to /health with ?token=... and /api/documents with ?token=...
        resp = client.get(f"/health?token={valid_token}")
        assert resp.status_code == 200

        resp2 = client.get(f"/api/invoices?token={valid_token}")
        # Could be 200 or 403/401 depending on test db state, but response must be valid HTTP
        assert resp2.status_code in (200, 401, 403, 404)

        captured_logs = stream.getvalue()
        assert "eyJ" not in captured_logs, f"JWT leaked in captured logs:\n{captured_logs}"
        if "token=" in captured_logs:
            assert "token=[REDACTED]" in captured_logs
    finally:
        root_logger.removeHandler(capture_handler)
        dms_access.removeHandler(capture_handler)
