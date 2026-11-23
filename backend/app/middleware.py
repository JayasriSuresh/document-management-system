"""
Request-ID middleware and structured logging configuration for DMS.

Every inbound request receives a unique X-Request-ID header that is:
  - Echoed back in the response
  - Injected into every log record emitted during that request via contextvars

Usage:
    from app.middleware import RequestIdMiddleware, configure_logging
    configure_logging()
    app.add_middleware(RequestIdMiddleware)
"""

import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.logging_redactor import RedactingFormatter, apply_redaction_filters

# ── Context variable so log records can include the request-id ───────────────
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_var.get()


# ── Log filter that injects request-id into every record ────────────────────
class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get("-")
        return True


# ── Middleware ────────────────────────────────────────────────────────────────
class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique request-id to every request and:
      - Stores it in a ContextVar so it appears in all log records
      - Returns it as X-Request-ID response header
      - Logs METHOD path → status_code in N ms
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = logging.getLogger("dms.access")

    async def dispatch(self, request: Request, call_next) -> Response:
        # Honour client-supplied id or generate a fresh one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id_var.set(request_id)

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            _request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id

        # Sanitised access log (no credentials, no query-string tokens)
        path = request.url.path
        self._logger.info(
            "%s %s → %d  [%.1f ms]  rid=%s",
            request.method,
            path,
            response.status_code,
            elapsed_ms,
            request_id,
        )

        # Record operational telemetry metrics
        try:
            from app.services.metrics_service import metrics_service
            metrics_service.record_http_request(request.method, path, response.status_code, elapsed_ms)
        except Exception:
            pass

        return response


# ── Logging configuration ─────────────────────────────────────────────────────
def configure_logging(level: str = "INFO") -> None:
    """
    Set up structured console logging with request-id injection and sensitive data redaction.

    Call once at application startup. Uses a format that is grep-friendly
    and easy to ship to log aggregators.
    """
    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | rid=%(request_id)s | %(message)s"
    )
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(RedactingFormatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers when uvicorn reloads
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)

    # Apply redaction filters and formatters across root, Uvicorn, and app loggers
    apply_redaction_filters()

    # Quieten noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)
