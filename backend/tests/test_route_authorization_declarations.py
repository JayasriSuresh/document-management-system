"""
Module 4 – Route-Level Permission Declaration & Enumeration Test.

Inspects all registered application routes in FastAPI and fails if any protected route
fails to declare an explicit authorization requirement via @requires or require_permission.
Maintains a small, explicit allowlist for genuinely public or session routes,
with documented explanations for each allowlisted route.
"""

from typing import Dict, List, Set
import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.auth.permissions import is_valid_permission


# ── Explicit Public Allowlist with Documented Explanations ─────────────────────
PUBLIC_ALLOWLIST: Dict[str, str] = {
    # System & Documentation
    "GET:/health": "Liveness and health check endpoint for monitoring and deployment probes.",
    "GET:/metrics": "Operational Prometheus metrics exposition endpoint for scrapers.",
    "GET:/api/metrics": "Operational JSON metrics telemetry endpoint for dashboards.",
    "GET:/{full_path:path}": "Frontend SPA static file catchall serving React dist/index.html.",
    "HEAD:/{full_path:path}": "Frontend SPA static file HEAD request handler.",
    "GET:/openapi.json": "OpenAPI schema definition for API clients.",
    "GET:/docs": "Swagger UI interactive API documentation.",
    "GET:/docs/oauth2-redirect": "OAuth2 redirect helper for Swagger UI.",
    "GET:/redoc": "ReDoc documentation UI.",

    # Public Media and Invoice Previews
    "GET:/api/company/logo": "Public company logo retrieval for branding.",
    "GET:/api/company/{company_id}/logo": "Public company logo retrieval by company ID.",
    "GET:/api/sales-invoices/signatures/temp/{token}": "Public token-gated temporary signature preview.",
    "GET:/api/sales-invoices/signatures/{sig_id}/image": "Signature image asset rendering.",
    "GET:/api/sales-invoices/{invoice_id}/preview-page": "Invoice rendered HTML/page preview.",
    "GET:/api/sales-invoices/drafts/{invoice_id}/preview-page": "Invoice draft rendered HTML/page preview.",

    # Identity & Public Workflows
    "POST:/api/auth/login": "Public entry point for user and administrator credential authentication.",
    "POST:/api/auth/refresh": "Public refresh token rotation endpoint using HttpOnly cookie session.",
    "POST:/api/auth/logout": "Session termination endpoint available to any authenticated identity.",
    "POST:/api/auth/logout-all": "Global session revocation endpoint available to any authenticated identity.",
    "POST:/api/auth/invite/accept": "Public token-gated invitation acceptance to activate invited user accounts.",
    "POST:/api/auth/password/reset-request": "Public rate-limited password recovery request endpoint.",
    "POST:/api/auth/password/reset": "Public token-gated password reset token redemption endpoint.",
    "POST:/api/auth/password/change": "Authenticated user password update endpoint.",
    "GET:/api/auth/me": "Identity profile discovery returning effective permissions and assignments for current user.",

    # Multi-Factor Authentication (MFA) Verification & Identity Lifecycle
    "POST:/api/auth/mfa/verify": "Step 2 TOTP verification endpoint redeeming mfa_pending_token.",
    "POST:/api/auth/mfa/recovery/verify": "Step 2 single-use recovery code redemption endpoint with mfa_pending_token.",
    "POST:/api/auth/mfa/enroll/start": "MFA enrollment initialization generating secret and QR SVG.",
    "POST:/api/auth/mfa/enroll/verify": "MFA enrollment verification and recovery code generation.",
    "GET:/api/auth/mfa/status": "MFA status check for current authenticated user or administrator.",
    "POST:/api/auth/mfa/disable": "Self-service MFA disablement with password and TOTP verification.",
    "POST:/api/auth/mfa/recovery/regenerate": "Self-service recovery codes regeneration with password/code verification.",

    # Prospective Company Public Onboarding (Token-Gated)
    "GET:/api/onboarding/{token}": "Public token-gated company onboarding application form viewer.",
    "POST:/api/onboarding/{token}/upload-document": "Public token-gated document upload for onboarding verification.",
    "GET:/api/onboarding/{token}/documents/{document_type}": "Public token-gated document download for applicant inspection.",
    "POST:/api/onboarding/{token}/submit": "Public token-gated onboarding application final submission.",
}


def _extract_all_routes(app_or_router) -> List[APIRoute]:
    """Recursively extract all APIRoutes registered on the FastAPI app."""
    routes = []
    for r in app_or_router.routes:
        if hasattr(r, "original_router"):
            routes.extend(_extract_all_routes(r.original_router))
        elif hasattr(r, "routes"):
            routes.extend(_extract_all_routes(r))
        elif isinstance(r, APIRoute):
            routes.append(r)
    return routes


def test_all_routes_declare_authorization_or_are_explicitly_allowlisted():
    """
    Startup / Route-Enumeration Test:
    Ensures that every registered endpoint declares a valid required permission,
    or is explicitly documented in the PUBLIC_ALLOWLIST.
    """
    routes = _extract_all_routes(app)
    assert len(routes) > 0, "No application routes found"

    missing_permission_routes = []
    invalid_permission_routes = []

    for route in routes:
        methods = route.methods or {"GET"}
        for method in methods:
            route_key = f"{method}:{route.path}"

            # Check if declared on endpoint via @requires
            declared_perm = getattr(route.endpoint, "__required_permission__", None)

            # Check if declared in dependencies via require_permission
            if not declared_perm and hasattr(route, "dependant"):
                for dep in route.dependant.dependencies:
                    if hasattr(dep.call, "__required_permission__"):
                        declared_perm = dep.call.__required_permission__
                        break

            if declared_perm:
                if not is_valid_permission(declared_perm):
                    invalid_permission_routes.append(f"{route_key} (Declared invalid permission: {declared_perm})")
            else:
                if route_key not in PUBLIC_ALLOWLIST:
                    missing_permission_routes.append(route_key)

    assert not invalid_permission_routes, (
        f"Found endpoints with invalid permission constants:\n"
        + "\n".join(invalid_permission_routes)
    )

    assert not missing_permission_routes, (
        f"Security Failure: The following protected endpoints lack authorization declarations:\n"
        + "\n".join(missing_permission_routes)
        + "\nEvery protected endpoint must use @requires(PERMISSION) or Depends(require_permission(PERMISSION))."
    )
