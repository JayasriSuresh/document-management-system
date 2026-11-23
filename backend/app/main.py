"""
DMS FastAPI application entry point.

Startup order:
  1. configure_logging()               — structured logs with request-id
  2. validate_production_config()      — hard-fail on bad config in production
  3. Base.metadata.create_all()        — idempotent table creation (dev/test)
  4. Middleware registration           — CORS, request-id
  5. Router registration               — auth, documents, invoices
  6. Error handlers                    — standardized JSON error shape
  7. Static frontend mount             — served last, after all API routes
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings, validate_production_config
from app.database import engine, Base
from app.logging_redactor import apply_redaction_filters
from app.middleware import RequestIdMiddleware, configure_logging
from app.routers import (
    auth,
    documents,
    invoices,
    admin,
    onboarding,
    company,
    audit,
    mfa,
    templates,
    review,
    gst_registrations,
    customers,
    sales_invoices,
    dashboard,
    branch_users,
)
from app.routers.ai import platform_ai_router, company_ai_router, branch_ai_router

# ── Logging must be first ──────────────────────────────────────────────────
configure_logging(level="DEBUG" if settings.is_development else "INFO")

logger = logging.getLogger("dms.startup")


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    apply_redaction_filters()
    validate_production_config(settings)
    logger.info(
        "Starting DMS | env=%s | db=%s",
        settings.APP_ENV,
        settings.DATABASE_URL.split("@")[-1],  # host/db only — no creds
    )

    # Idempotent table creation — Alembic handles migrations in production,
    # but create_all ensures the dev / test environments bootstrap cleanly.
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified.")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("DMS shutdown complete.")


# ── Application factory ────────────────────────────────────────────────────
app = FastAPI(
    title="DMS API",
    description="Document Management System — backend API",
    version="1.0.0",
    # Disable automatic OpenAPI/Swagger in production to reduce attack surface
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)


# ── Middleware ─────────────────────────────────────────────────────────────
# 1. Request-ID (innermost — must wrap business logic)
app.add_middleware(RequestIdMiddleware)

# 2. CORS
#    In production, CORS_ORIGINS must be a comma-separated list of
#    allowed frontend origins, not '*'.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Standardised error handlers ────────────────────────────────────────────
def _error_body(status_code: int, detail: str, request_id: str) -> dict:
    return {
        "error": {
            "status": status_code,
            "detail": detail,
            "request_id": request_id,
        }
    }


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    rid = request.headers.get("X-Request-ID", "-")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=_error_body(404, "Resource not found", rid),
    )


@app.exception_handler(405)
async def method_not_allowed_handler(request: Request, exc):
    rid = request.headers.get("X-Request-ID", "-")
    return JSONResponse(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        content=_error_body(405, "Method not allowed", rid),
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    rid = request.headers.get("X-Request-ID", "-")
    logger.exception("Unhandled error [rid=%s]", rid, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(500, "Internal server error", rid),
    )


# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(invoices.router)
app.include_router(admin.router)
app.include_router(onboarding.router)
app.include_router(company.router)
app.include_router(audit.router)
app.include_router(mfa.router)
app.include_router(platform_ai_router)
app.include_router(company_ai_router)
app.include_router(branch_ai_router)
app.include_router(templates.router)
app.include_router(review.router)
app.include_router(gst_registrations.router)
app.include_router(customers.router)
app.include_router(sales_invoices.router)
app.include_router(dashboard.router)
app.include_router(branch_users.router)


# ── Health check ───────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "env": settings.APP_ENV}


# ── Operational Metrics & Telemetry ────────────────────────────────────────
@app.get("/metrics", tags=["ops"])
def prometheus_metrics():
    from fastapi.responses import PlainTextResponse
    from app.services.metrics_service import metrics_service
    return PlainTextResponse(metrics_service.to_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/metrics", tags=["ops"])
def json_metrics():
    from app.services.metrics_service import metrics_service
    return metrics_service.get_summary()


# ── React frontend static files (must come LAST — after all API routes) ───
frontend_path = Path(__file__).parent.parent.parent / "frontend" / "dist"

if frontend_path.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=frontend_path / "assets"),
        name="frontend-assets",
    )

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    def serve_frontend(request: Request, full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=_error_body(404, "Not found", "-"),
            )
        return FileResponse(frontend_path / "index.html")
