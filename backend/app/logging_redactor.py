"""
DMS Sensitive Data Logging Redactor.

Ensures that JWT tokens, query parameter secrets, passwords, Bearer headers,
and authentication credentials are NEVER exposed in:
  - Terminal output
  - Uvicorn access / error logs
  - Application access logs (dms.access)
  - Exception tracebacks (exc_info)
  - Background worker logs (dms.worker)
"""

import copy
import logging
import re
from typing import Any

try:
    from uvicorn.logging import AccessFormatter as UvicornAccessFormatter
    from uvicorn.logging import DefaultFormatter as UvicornDefaultFormatter
except ImportError:
    UvicornAccessFormatter = None
    UvicornDefaultFormatter = None

SENSITIVE_PARAM_NAMES = [
    "token",
    "access_token",
    "refresh_token",
    "mfa_pending_token",
    "enrollment_token",
    "reset_token",
    "invite_token",
    "auth_token",
    "session_token",
    "password",
    "passwd",
    "new_password",
    "confirm_password",
    "current_password",
    "secret",
    "client_secret",
    "secret_key",
    "api_key",
    "apikey",
    "key",
    "otp",
    "code",
    "totp",
    "totp_code",
    "recovery_code",
    "session",
    "session_id",
]

_NAMES_PATTERN = "|".join(re.escape(name) for name in SENSITIVE_PARAM_NAMES)

# 1. URL Query parameters: ?token=xxx or &token=xxx
QUERY_PARAM_REGEX = re.compile(
    rf"(?<=[?&])(?:{_NAMES_PATTERN})=[^&\s]+",
    re.IGNORECASE,
)

# 2. Authorization: Bearer tokens
BEARER_REGEX = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9_\.\-]+",
    re.IGNORECASE,
)

# 3. Standalone JWT tokens: eyJ...
JWT_REGEX = re.compile(
    r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+"
)

# 4. Key-value pairs (JSON, URL-encoded, Python dict representation, etc.):
KEY_VALUE_REGEX = re.compile(
    rf'''(?i)(["']?(?:{_NAMES_PATTERN})["']?\s*[:=]\s*["']?)(?:bearer\s+)?[^"'\s,;&}}]+''',
    re.IGNORECASE,
)

# 5. Cookie headers or values: token=xxx; session=xxx
COOKIE_REGEX = re.compile(
    rf"(?i)((?:{_NAMES_PATTERN})=)[^;\s&?]+",
    re.IGNORECASE,
)


def redact_sensitive_data(val: Any) -> Any:
    """Recursively redacts sensitive authentication information from strings and data structures."""
    if isinstance(val, str):
        v = QUERY_PARAM_REGEX.sub(lambda m: m.group(0).split("=")[0] + "=[REDACTED]", val)
        v = BEARER_REGEX.sub(r"\1[REDACTED]", v)
        v = JWT_REGEX.sub("[REDACTED_JWT]", v)
        v = KEY_VALUE_REGEX.sub(r"\1[REDACTED]", v)
        v = COOKIE_REGEX.sub(r"\1[REDACTED]", v)
        return v
    elif isinstance(val, tuple):
        return tuple(redact_sensitive_data(x) for x in val)
    elif isinstance(val, list):
        return [redact_sensitive_data(x) for x in val]
    elif isinstance(val, dict):
        result = {}
        for k, v in val.items():
            k_lower = str(k).lower()
            if k_lower in SENSITIVE_PARAM_NAMES:
                result[k] = "[REDACTED]"
            else:
                result[k] = redact_sensitive_data(v)
        return result
    elif isinstance(val, set):
        return {redact_sensitive_data(x) for x in val}
    return val


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that redacts sensitive authentication data from log records.
    Modifies record.msg, record.args, and record.exc_text in-place.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # If arguments exist, record.msg is a format string template containing
            # specifiers like %s. We redact record.args directly so format specifiers
            # aren't corrupted before getMessage() runs.
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(redact_sensitive_data(x) for x in record.args)
                elif isinstance(record.args, dict):
                    record.args = {k: redact_sensitive_data(v) for k, v in record.args.items()}
                else:
                    record.args = redact_sensitive_data(record.args)
            else:
                if isinstance(record.msg, str):
                    record.msg = redact_sensitive_data(record.msg)

            # Redact tracebacks / exceptions
            if record.exc_info and not record.exc_text:
                raw_exc = logging.Formatter().formatException(record.exc_info)
                record.exc_text = redact_sensitive_data(raw_exc)
            elif getattr(record, "exc_text", None):
                record.exc_text = redact_sensitive_data(record.exc_text)

            if getattr(record, "stack_info", None):
                record.stack_info = redact_sensitive_data(record.stack_info)
        except Exception:
            pass  # Never fail logging
        return True


class RedactingFormatter(logging.Formatter):
    """
    Standard logging formatter that applies redaction to the formatted message,
    tracebacks, and stack traces.
    """

    def format(self, record: logging.LogRecord) -> str:
        s = super().format(record)
        return redact_sensitive_data(s)

    def formatException(self, ei) -> str:
        s = super().formatException(ei)
        return redact_sensitive_data(s)

    def formatStack(self, stack_info) -> str:
        s = super().formatStack(stack_info)
        return redact_sensitive_data(s)


if UvicornAccessFormatter is not None:
    class RedactingUvicornAccessFormatter(UvicornAccessFormatter):
        """Redacting variant of Uvicorn AccessFormatter preserving colors and styles."""

        def format(self, record: logging.LogRecord) -> str:
            s = super().format(record)
            return redact_sensitive_data(s)

        def formatException(self, ei) -> str:
            s = super().formatException(ei)
            return redact_sensitive_data(s)
else:
    RedactingUvicornAccessFormatter = RedactingFormatter


if UvicornDefaultFormatter is not None:
    class RedactingUvicornDefaultFormatter(UvicornDefaultFormatter):
        """Redacting variant of Uvicorn DefaultFormatter preserving colors and styles."""

        def format(self, record: logging.LogRecord) -> str:
            s = super().format(record)
            return redact_sensitive_data(s)

        def formatException(self, ei) -> str:
            s = super().formatException(ei)
            return redact_sensitive_data(s)
else:
    RedactingUvicornDefaultFormatter = RedactingFormatter


def _wrap_handler_formatter(handler: logging.Handler) -> None:
    """Wraps or upgrades a handler's formatter to a redacting equivalent."""
    if not handler.formatter:
        return

    curr = handler.formatter
    if isinstance(
        curr,
        (RedactingFormatter, RedactingUvicornAccessFormatter, RedactingUvicornDefaultFormatter),
    ):
        return

    fmt = getattr(curr, "_fmt", None)
    datefmt = getattr(curr, "datefmt", None)
    use_colors = getattr(curr, "use_colors", None)

    if UvicornAccessFormatter and isinstance(curr, UvicornAccessFormatter):
        handler.setFormatter(
            RedactingUvicornAccessFormatter(fmt=fmt, datefmt=datefmt, use_colors=use_colors)
        )
    elif UvicornDefaultFormatter and isinstance(curr, UvicornDefaultFormatter):
        handler.setFormatter(
            RedactingUvicornDefaultFormatter(fmt=fmt, datefmt=datefmt, use_colors=use_colors)
        )
    else:
        handler.setFormatter(RedactingFormatter(fmt=fmt, datefmt=datefmt))


def apply_redaction_filters() -> None:
    """
    Installs SensitiveDataFilter and RedactingFormatter across root,
    Uvicorn, and DMS application loggers and their handlers.
    """
    sensitive_filter = SensitiveDataFilter()

    target_loggers = [
        "",  # root
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "dms.access",
        "dms.startup",
        "dms.worker",
        "fastapi",
    ]

    for logger_name in target_loggers:
        logger = logging.getLogger(logger_name)
        if not any(isinstance(f, SensitiveDataFilter) for f in logger.filters):
            logger.addFilter(sensitive_filter)

        for handler in logger.handlers:
            if not any(isinstance(f, SensitiveDataFilter) for f in handler.filters):
                handler.addFilter(sensitive_filter)
            _wrap_handler_formatter(handler)

    # Also sanitize any existing loggers in the manager dictionary
    for name, item in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(item, logging.Logger):
            if not any(isinstance(f, SensitiveDataFilter) for f in item.filters):
                item.addFilter(sensitive_filter)
            for handler in item.handlers:
                if not any(isinstance(f, SensitiveDataFilter) for f in handler.filters):
                    handler.addFilter(sensitive_filter)
                _wrap_handler_formatter(handler)
