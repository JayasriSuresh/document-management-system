"""
Module 5 – Centralized Audit Event Constants and Actor Types.
"""

from enum import Enum


class ActorType(str, Enum):
    MASTER_ADMIN = "master_admin"
    COMPANY_USER = "company_user"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"


class ObjectType(str, Enum):
    DOCUMENT = "document"
    INVOICE = "invoice"
    USER = "user"
    COMPANY = "company"
    BRANCH = "branch"
    SESSION = "session"
    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"
    AI_CONFIG = "ai_config"
    TEMPLATE = "template"
    EXTRACTION = "extraction"
    ONBOARDING = "onboarding"
    MFA = "mfa"
    SECURITY_POLICY = "security_policy"
    CUSTOMER = "customer"
    GST_REGISTRATION = "gst_registration"
    AI_MODEL = "ai_model"
    AI_ASSIGNMENT = "ai_assignment"
    AI_REQUEST = "ai_request"


# ── Audit Event Types ──────────────────────────────────────────────────────────

# A. Authentication & Sessions
AUTH_LOGIN_SUCCESS = "auth.login.success"
AUTH_LOGIN_FAILURE = "auth.login.failure"
AUTH_LOGOUT = "auth.logout"
AUTH_LOGOUT_ALL = "auth.logout_all"
AUTH_SESSION_REVOKE = "auth.session.revoke"
AUTH_TOKEN_REFRESH = "auth.token.refresh"
AUTH_TOKEN_REPLAY_DETECTED = "auth.token.replay_detected"
AUTH_ACCOUNT_LOCKOUT = "auth.account.lockout"
AUTH_ACCOUNT_UNLOCK = "auth.account.unlock"
AUTH_PASSWORD_CHANGE = "auth.password.change"
AUTH_PASSWORD_RESET_REQUEST = "auth.password.reset_request"
AUTH_PASSWORD_RESET_SUCCESS = "auth.password.reset_success"
AUTH_INVITATION_CREATE = "auth.invitation.create"
AUTH_INVITATION_ACCEPT = "auth.invitation.accept"
AUTH_INVITATION_EXPIRE = "auth.invitation.expire"
AUTH_INVITATION_REVOKE = "auth.invitation.revoke"

# B. MFA Events
AUTH_MFA_ENROLL_START = "auth.mfa.enroll_start"
AUTH_MFA_ENROLL_COMPLETE = "auth.mfa.enroll_complete"
AUTH_MFA_VERIFY_SUCCESS = "auth.mfa.verify_success"
AUTH_MFA_VERIFY_FAILURE = "auth.mfa.verify_failure"
AUTH_MFA_RECOVERY_SUCCESS = "auth.mfa.recovery_success"
AUTH_MFA_RECOVERY_FAILURE = "auth.mfa.recovery_failure"
AUTH_MFA_RECOVERY_REGENERATE = "auth.mfa.recovery_regenerate"
AUTH_MFA_DISABLE = "auth.mfa.disable"
AUTH_MFA_RESET_BY_ADMIN = "auth.mfa.reset_by_admin"
AUTH_MFA_POLICY_UPDATE = "auth.mfa.policy_update"

# C. User & Authorization Management
USER_CREATE = "user.create"
USER_UPDATE = "user.update"
USER_DEACTIVATE = "user.deactivate"
USER_REACTIVATE = "user.reactivate"
ROLE_ASSIGN = "role.assign"
ROLE_REMOVE = "role.remove"
PERMISSION_SCOPE_CHANGE = "permission.scope_change"
BRANCH_ASSIGNMENT_CHANGE = "branch.assignment_change"

# D. Document Operations
DOCUMENT_UPLOAD = "document.upload"
DOCUMENT_VIEW = "document.view"
DOCUMENT_DOWNLOAD = "document.download"
DOCUMENT_EDIT = "document.edit"
DOCUMENT_DELETE = "document.delete"
DOCUMENT_RESTORE = "document.restore"
DOCUMENT_REPROCESS = "document.reprocess"
DOCUMENT_EXPORT = "document.export"
DOCUMENT_ACCESS_DENIED = "document.access_denied"

# E. AI Configuration
AI_CONFIG_UPDATE = "ai.config.update"
AI_PROVIDER_SELECT = "ai.provider.select"
AI_MODEL_SELECT = "ai.model.select"
AI_CONFIG_TOGGLE = "ai.config.toggle"
AI_CREDENTIAL_CREATE = "ai.credential.create"
AI_CREDENTIAL_DELETE = "ai.credential.delete"
AI_CONSENT_GRANT = "ai.consent.grant"
AI_CONSENT_REVOKE = "ai.consent.revoke"
AI_CONNECTION_TEST = "ai.connection.test"
AI_BUDGET_EXHAUSTED = "ai.budget.exhausted"
AI_MODEL_CATALOGUE_UPDATE = "ai.model_catalogue.update"
AI_MODEL_ASSIGNMENT_UPDATE = "ai.model_assignment.update"
AI_MODEL_REQUEST_CREATE = "ai.model_request.create"
AI_MODEL_REQUEST_APPROVE = "ai.model_request.approve"
AI_MODEL_REQUEST_REJECT = "ai.model_request.reject"

# F. Invoice Templates & Document Templates (Module 11)
TEMPLATE_CREATE = "template.create"
TEMPLATE_UPDATE = "template.update"
TEMPLATE_DELETE = "template.delete"
TEMPLATE_TOGGLE = "template.toggle"
TEMPLATE_VERSION_CREATE = "template.version.create"
TEMPLATE_VERSION_PUBLISH = "template.version.publish"
TEMPLATE_DEACTIVATE = "template.deactivate"

# Extraction & Human Review Events (Module 11)
EXTRACTION_EDIT = "extraction.edit"
EXTRACTION_REVIEW_SUBMIT = "extraction.review.submit"
EXTRACTION_APPROVE = "extraction.approve"
EXTRACTION_OVERRIDE = "extraction.override"
EXTRACTION_REPROCESS = "extraction.reprocess"

# G. Company & Branch Management
COMPANY_CREATE = "company.create"
COMPANY_UPDATE = "company.update"
COMPANY_SUSPEND = "company.suspend"
COMPANY_ACTIVATE = "company.activate"
BRANCH_CREATE = "branch.create"
BRANCH_UPDATE = "branch.update"
BRANCH_TOGGLE = "branch.toggle"

# H. Master Admin Operations
MASTER_ADMIN_COMPANY_VIEW = "master_admin.company.view"
MASTER_ADMIN_WORKSPACE_ENTER = "master_admin.company.workspace_enter"
MASTER_ADMIN_CONTEXT_SWITCH = "master_admin.company.context_switch"
MASTER_ADMIN_COMPANY_UPDATE = "master_admin.company.update"
MASTER_ADMIN_COMPANY_SUSPEND = "master_admin.company.suspend"
MASTER_ADMIN_COMPANY_ACTIVATE = "master_admin.company.activate"
MASTER_ADMIN_COMPANY_QUOTA_UPDATE = "master_admin.company.quota_update"
MASTER_ADMIN_SETTINGS_UPDATE = "master_admin.settings.update"
MASTER_ADMIN_PROVIDER_TOGGLE = "master_admin.provider.toggle"
MASTER_ADMIN_USER_MANAGE = "master_admin.user.manage"
MASTER_ADMIN_ONBOARDING_REVIEW = "master_admin.onboarding.review"

# I. Module 13 – Inbound & Outbound Invoices
SALES_INVOICE_DRAFT_CREATED = "invoice.sales.draft_created"
SALES_INVOICE_DRAFT_UPDATED = "invoice.sales.draft_updated"
SALES_INVOICE_DRAFT_DISCARDED = "invoice.sales.draft_discarded"
SALES_INVOICE_SUBMITTED = "invoice.sales.submitted"
SALES_INVOICE_APPROVED = "invoice.sales.approved"
SALES_INVOICE_REJECTED = "invoice.sales.rejected"
SALES_INVOICE_CANCELLED = "invoice.sales.cancelled"
SUPPLIER_COPY_REGENERATED = "invoice.copy.regenerated"

# J. Master Data (Customers & GST Registrations)
CUSTOMER_CREATE = "customer.create"
CUSTOMER_UPDATE = "customer.update"
GST_REGISTRATION_CREATE = "gst_registration.create"
GST_REGISTRATION_UPDATE = "gst_registration.update"


