"""
Module 4 – Role-to-Permission Mapping.

Defines role permissions in code and provides migration mappings from legacy roles.
"""

from typing import Dict, FrozenSet, Set
from app.auth.permissions import (
    ALL_PERMISSIONS,
    AUDIT_VIEW_BRANCH,
    AUDIT_VIEW_COMPANY,
    AUDIT_VIEW_PLATFORM,
    BRANCH_CREATE,
    BRANCH_EDIT,
    BRANCH_VIEW,
    COMPANY_MANAGE,
    COMPANY_VIEW,
    DOCUMENT_DELETE,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_REPROCESS,
    DOCUMENT_SEARCH,
    DOCUMENT_UPLOAD,
    DOCUMENT_VIEW_BRANCH,
    DOCUMENT_VIEW_COMPANY,
    DOCUMENT_VIEW_HISTORY,
    DOCUMENT_VIEW_OWN,
    INVOICE_CREATE,
    INVOICE_DOWNLOAD,
    INVOICE_VIEW,
    INVOICE_SALES_CREATE,
    INVOICE_SALES_EDIT,
    INVOICE_SALES_DISCARD,
    INVOICE_SALES_SUBMIT,
    INVOICE_SALES_APPROVE,
    INVOICE_SALES_CANCEL,
    INVOICE_SALES_VIEW,
    CUSTOMER_MANAGE,
    CUSTOMER_VIEW,
    GST_REGISTRATION_MANAGE,
    GST_REGISTRATION_VIEW,
    MFA_MANAGE_COMPANY,
    MFA_MANAGE_PLATFORM,
    PLATFORM_MANAGE,
    USER_ASSIGN_ROLE,
    USER_DEACTIVATE,
    USER_INVITE,
    USER_VIEW,
    AI_SETTINGS_VIEW,
    AI_SETTINGS_MANAGE,
    AI_USAGE_VIEW,
    TEMPLATE_VIEW,
    TEMPLATE_CREATE,
    TEMPLATE_UPDATE,
    TEMPLATE_PUBLISH,
    TEMPLATE_DELETE,
    EXTRACTION_VIEW,
    EXTRACTION_REVIEW,
    EXTRACTION_EDIT,
    EXTRACTION_APPROVE,
    EXTRACTION_REPROCESS,
    EXTRACTION_OVERRIDE,
)

# ── Canonical Role Identifiers ────────────────────────────────────────────────
ROLE_GLOBAL_ADMIN = "GLOBAL_ADMIN"
ROLE_ADMIN = "ADMIN"
ROLE_STAFF = "STAFF"
ROLE_UPLOADER = "UPLOADER"
ROLE_MASTER_ADMIN = "MASTER_ADMIN"


# ── Role Permissions Map ──────────────────────────────────────────────────────
ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    ROLE_GLOBAL_ADMIN: frozenset({
        DOCUMENT_UPLOAD,
        DOCUMENT_VIEW_OWN,
        DOCUMENT_VIEW_BRANCH,
        DOCUMENT_VIEW_COMPANY,
        DOCUMENT_SEARCH,
        DOCUMENT_DOWNLOAD,
        DOCUMENT_DELETE,
        DOCUMENT_REPROCESS,
        DOCUMENT_VIEW_HISTORY,
        INVOICE_VIEW,
        INVOICE_DOWNLOAD,
        INVOICE_CREATE,
        INVOICE_SALES_CREATE,
        INVOICE_SALES_EDIT,
        INVOICE_SALES_DISCARD,
        INVOICE_SALES_SUBMIT,
        INVOICE_SALES_APPROVE,
        INVOICE_SALES_CANCEL,
        INVOICE_SALES_VIEW,
        CUSTOMER_MANAGE,
        CUSTOMER_VIEW,
        GST_REGISTRATION_MANAGE,
        GST_REGISTRATION_VIEW,
        USER_VIEW,
        USER_INVITE,
        USER_ASSIGN_ROLE,
        USER_DEACTIVATE,
        BRANCH_VIEW,
        BRANCH_CREATE,
        BRANCH_EDIT,
        COMPANY_VIEW,
        COMPANY_MANAGE,
        AUDIT_VIEW_COMPANY,
        AUDIT_VIEW_BRANCH,
        MFA_MANAGE_COMPANY,
        AI_SETTINGS_VIEW,
        AI_SETTINGS_MANAGE,
        AI_USAGE_VIEW,
        TEMPLATE_VIEW,
        TEMPLATE_CREATE,
        TEMPLATE_UPDATE,
        TEMPLATE_PUBLISH,
        TEMPLATE_DELETE,
        EXTRACTION_VIEW,
        EXTRACTION_REVIEW,
        EXTRACTION_EDIT,
        EXTRACTION_APPROVE,
        EXTRACTION_REPROCESS,
        EXTRACTION_OVERRIDE,
    }),
    ROLE_ADMIN: frozenset({
        DOCUMENT_UPLOAD,
        DOCUMENT_VIEW_OWN,
        DOCUMENT_VIEW_BRANCH,
        DOCUMENT_SEARCH,
        DOCUMENT_DOWNLOAD,
        DOCUMENT_DELETE,
        DOCUMENT_REPROCESS,
        DOCUMENT_VIEW_HISTORY,
        INVOICE_VIEW,
        INVOICE_DOWNLOAD,
        INVOICE_CREATE,
        INVOICE_SALES_CREATE,
        INVOICE_SALES_EDIT,
        INVOICE_SALES_DISCARD,
        INVOICE_SALES_SUBMIT,
        INVOICE_SALES_APPROVE,
        INVOICE_SALES_CANCEL,
        INVOICE_SALES_VIEW,
        CUSTOMER_MANAGE,
        CUSTOMER_VIEW,
        GST_REGISTRATION_MANAGE,
        GST_REGISTRATION_VIEW,
        USER_VIEW,
        USER_INVITE,
        BRANCH_VIEW,
        AUDIT_VIEW_BRANCH,
        AI_SETTINGS_VIEW,
        AI_USAGE_VIEW,
        TEMPLATE_VIEW,
        TEMPLATE_CREATE,
        TEMPLATE_UPDATE,
        TEMPLATE_PUBLISH,
        TEMPLATE_DELETE,
        EXTRACTION_VIEW,
        EXTRACTION_REVIEW,
        EXTRACTION_EDIT,
        EXTRACTION_APPROVE,
        EXTRACTION_REPROCESS,
        EXTRACTION_OVERRIDE,
    }),
    ROLE_STAFF: frozenset({
        DOCUMENT_UPLOAD,
        DOCUMENT_VIEW_OWN,
        DOCUMENT_SEARCH,
        DOCUMENT_DOWNLOAD,
        INVOICE_VIEW,
        INVOICE_DOWNLOAD,
        INVOICE_SALES_CREATE,
        INVOICE_SALES_EDIT,
        INVOICE_SALES_DISCARD,
        INVOICE_SALES_SUBMIT,
        INVOICE_SALES_VIEW,
        CUSTOMER_VIEW,
        GST_REGISTRATION_VIEW,
        TEMPLATE_VIEW,
        EXTRACTION_VIEW,
        EXTRACTION_REVIEW,
        EXTRACTION_EDIT,
    }),
    ROLE_UPLOADER: frozenset({
        DOCUMENT_UPLOAD,
        DOCUMENT_VIEW_OWN,
        DOCUMENT_SEARCH,
        DOCUMENT_DOWNLOAD,
        INVOICE_VIEW,
        INVOICE_DOWNLOAD,
        INVOICE_SALES_VIEW,
        CUSTOMER_VIEW,
        GST_REGISTRATION_VIEW,
        TEMPLATE_VIEW,
        EXTRACTION_VIEW,
    }),
    ROLE_MASTER_ADMIN: frozenset({
        PLATFORM_MANAGE,
        AUDIT_VIEW_PLATFORM,
        MFA_MANAGE_PLATFORM,
        MFA_MANAGE_COMPANY,
        AI_SETTINGS_VIEW,
        AI_SETTINGS_MANAGE,
        AI_USAGE_VIEW,
        TEMPLATE_VIEW,
    }),
}


# ── Explicit Migration Mapping Table ──────────────────────────────────────────
# | Existing Role | New Role   | Scope Type | Permitted Behavior Description                               |
# |---------------|------------|------------|--------------------------------------------------------------|
# | GLOBAL_ADMIN  | GLOBAL_ADMIN | company  | Full company-wide document, invoice, user, branch management |
# | ADMIN         | ADMIN      | branch     | Full branch-scoped document, invoice, and branch user invite |
# | STAFF         | UPLOADER   | branch     | Own-document upload, view, download, search within 30-day cutoff |
LEGACY_ROLE_MIGRATION = {
    "GLOBAL_ADMIN": {
        "new_role": ROLE_GLOBAL_ADMIN,
        "scope_type": "company",
        "description": "Company-wide administration across all branches",
    },
    "ADMIN": {
        "new_role": ROLE_ADMIN,
        "scope_type": "branch",
        "description": "Branch-scoped administrator",
    },
    "STAFF": {
        "new_role": ROLE_UPLOADER,
        "scope_type": "branch",
        "description": "Branch-scoped Uploader with 30-day own-document restriction",
    },
}


def get_permissions_for_role(role: str) -> Set[str]:
    """Retrieve the set of permissions associated with a given role."""
    return set(ROLE_PERMISSIONS.get(role, set()))


def get_effective_permissions(roles: Set[str]) -> Set[str]:
    """Calculate the union of permissions across all assigned roles."""
    perms = set()
    for r in roles:
        perms.update(ROLE_PERMISSIONS.get(r, set()))
    return perms

