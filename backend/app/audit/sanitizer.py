"""
Module 5 – Sensitive Data Protection & Metadata Sanitization.

Enforces an explicit allowlist and strict deny patterns to guarantee
no secrets, passwords, tokens, API keys, or raw OCR/document bodies
can enter audit logs.
"""

from typing import Any, Dict, Set


# Keys that are strictly forbidden regardless of casing or nesting
FORBIDDEN_KEY_SUBSTRINGS = (
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "apikey",
    "gemini_key",
    "auth_header",
    "authorization",
    "cookie",
    "otp",
    "totp",
    "recovery_code",
    "ocr_text",
    "extracted_text",
    "raw_body",
    "full_document",
    "file_data",
    "file_content",
    "database_url",
    "connection_string",
)

# Explicitly allowed safe metadata keys
ALLOWED_METADATA_KEYS: Set[str] = {
    # File & Document metadata
    "filename",
    "original_filename",
    "file_size",
    "mime_type",
    "storage_key",
    "document_id",
    "invoice_id",
    "invoice_number",
    "invoice_date",
    "currency",
    "reprocess_status",
    "ocr_status",
    "pages_count",
    "download_format",
    # User & Identity metadata
    "email",
    "name",
    "user_id",
    "role",
    "roles",
    "previous_role",
    "new_role",
    "scope_type",
    "scope_id",
    "account_status",
    "is_active",
    "must_change_password",
    # Company & Branch metadata
    "company_id",
    "company_name",
    "company_code",
    "branch_id",
    "branch_name",
    "branch_code",
    "branch_type",
    "previous_status",
    "new_status",
    "city",
    "state",
    # Administrative & Review decisions
    "decision",
    "reason",
    "comment",
    "rejection_reason",
    "application_id",
    "submitted_at",
    "lockout_minutes",
    "failed_attempts",
    # AI & Template configuration (names only, no secrets!)
    "provider",
    "model",
    "template_id",
    "template_name",
    "enabled",
    # Query & Search context
    "query",
    "search_term",
    "count",
    "items_count",
    "page",
    "page_size",
    "session_id",
    "revocation_type",
    # MFA & Security Policy
    "mfa_method",
    "mfa_enabled",
    "mfa_required",
    "remaining_recovery_codes",
    "policy_key",
    "policy_value",
    "reset_by",
    "target_user_id",
    "target_admin_id",
    "enforce_master_admin",
    "enforce_company_admin",
    "enforce_all",
    "mfa_required_for_all",
}


def is_forbidden_key(key: str) -> bool:
    """Check if key contains any forbidden substring."""
    key_lower = key.lower()
    for forbidden in FORBIDDEN_KEY_SUBSTRINGS:
        if forbidden in key_lower:
            return True
    return False


def sanitize_value(val: Any, depth: int = 0) -> Any:
    """Recursively sanitize metadata value."""
    if depth > 3:
        return "[MAX_DEPTH_EXCEEDED]"

    if val is None or isinstance(val, (bool, int, float)):
        return val

    if isinstance(val, str):
        # Truncate strings to prevent large payload dumps
        if len(val) > 500:
            return val[:497] + "..."
        return val

    if isinstance(val, (list, tuple)):
        # Limit array length
        return [sanitize_value(item, depth + 1) for item in list(val)[:20]]

    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            k_str = str(k)
            # Only permit keys in allowlist and not matching forbidden substrings
            if k_str in ALLOWED_METADATA_KEYS and not is_forbidden_key(k_str):
                sanitized[k_str] = sanitize_value(v, depth + 1)
        return sanitized

    return str(val)[:100]


def sanitize_metadata(metadata: Any) -> Dict[str, Any]:
    """
    Sanitize metadata dictionary according to explicit allowlist.
    Returns clean, safe dictionary ready for JSONB insertion.
    """
    if not metadata or not isinstance(metadata, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for key, value in metadata.items():
        key_str = str(key)
        # Check against forbidden keywords and allowlist
        if is_forbidden_key(key_str):
            continue
        if key_str in ALLOWED_METADATA_KEYS:
            sanitized[key_str] = sanitize_value(value, depth=0)

    return sanitized

