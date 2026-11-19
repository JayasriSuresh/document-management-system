"""
Module 4 – Centralized Permission Definitions.

All permission identifiers are defined here as stable constants.
No hardcoded string literals should be scattered throughout the application.
"""

from typing import FrozenSet, Set


# ── Document Permissions ─────────────────────────────────────────────────────
DOCUMENT_UPLOAD = "document.upload"
DOCUMENT_VIEW_OWN = "document.view_own"
DOCUMENT_VIEW_BRANCH = "document.view_branch"
DOCUMENT_VIEW_COMPANY = "document.view_company"
DOCUMENT_SEARCH = "document.search"
DOCUMENT_DOWNLOAD = "document.download"
DOCUMENT_DELETE = "document.delete"
DOCUMENT_REPROCESS = "document.reprocess"
DOCUMENT_VIEW_HISTORY = "document.view_history"

# ── Invoice Permissions ──────────────────────────────────────────────────────
INVOICE_VIEW = "invoice.view"
INVOICE_DOWNLOAD = "invoice.download"
INVOICE_CREATE = "invoice.create"

# ── Module 13: Outbound Sales Invoices & Master Data Permissions ──────────────
INVOICE_SALES_CREATE = "invoice.sales.create"
INVOICE_SALES_EDIT = "invoice.sales.edit"
INVOICE_SALES_DISCARD = "invoice.sales.discard"
INVOICE_SALES_SUBMIT = "invoice.sales.submit"
INVOICE_SALES_APPROVE = "invoice.sales.approve"
INVOICE_SALES_CANCEL = "invoice.sales.cancel"
INVOICE_SALES_VIEW = "invoice.sales.view"

CUSTOMER_MANAGE = "customer.manage"
CUSTOMER_VIEW = "customer.view"

GST_REGISTRATION_MANAGE = "gst_registration.manage"
GST_REGISTRATION_VIEW = "gst_registration.view"

# ── Administration Permissions ───────────────────────────────────────────────
USER_VIEW = "user.view"
USER_INVITE = "user.invite"
USER_ASSIGN_ROLE = "user.assign_role"
USER_DEACTIVATE = "user.deactivate"

BRANCH_VIEW = "branch.view"
BRANCH_CREATE = "branch.create"
BRANCH_EDIT = "branch.edit"

COMPANY_VIEW = "company.view"
COMPANY_MANAGE = "company.manage"

# ── Audit Log Permissions (Module 5) ─────────────────────────────────────────
AUDIT_VIEW_COMPANY = "audit.view_company"
AUDIT_VIEW_BRANCH = "audit.view_branch"
AUDIT_VIEW_PLATFORM = "audit.view_platform"

# ── Multi-Factor Authentication Permissions (Module 6) ───────────────────────
MFA_MANAGE_COMPANY = "mfa.manage_company"
MFA_MANAGE_PLATFORM = "mfa.manage_platform"

# ── Platform Master Admin Permissions ─────────────────────────────────────────
PLATFORM_MANAGE = "platform.manage"

# ── AI Configuration & Usage Permissions (Module 10) ─────────────────────────
AI_SETTINGS_VIEW = "ai.settings.view"
AI_SETTINGS_MANAGE = "ai.settings.manage"
AI_USAGE_VIEW = "ai.usage.view"

# ── Extraction Template & Human Verification Permissions (Module 11) ─────────
TEMPLATE_VIEW = "template.view"
TEMPLATE_CREATE = "template.create"
TEMPLATE_UPDATE = "template.update"
TEMPLATE_PUBLISH = "template.publish"
TEMPLATE_DELETE = "template.delete"

EXTRACTION_VIEW = "extraction.view"
EXTRACTION_REVIEW = "extraction.review"
EXTRACTION_EDIT = "extraction.edit"
EXTRACTION_APPROVE = "extraction.approve"
EXTRACTION_REPROCESS = "extraction.reprocess"
EXTRACTION_OVERRIDE = "extraction.override_validation"


ALL_PERMISSIONS: FrozenSet[str] = frozenset({
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
    AUDIT_VIEW_PLATFORM,
    MFA_MANAGE_COMPANY,
    MFA_MANAGE_PLATFORM,
    PLATFORM_MANAGE,
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
})


def is_valid_permission(perm: str) -> bool:
    """Validate that a permission identifier is officially recognized."""
    return perm in ALL_PERMISSIONS

