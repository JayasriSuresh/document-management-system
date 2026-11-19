from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union, List, Dict, Any

from pydantic import BaseModel, Field, AliasChoices

from app.models import UserRole, OcrStatus, CompanyStatus, OnboardingStatus


# ── Auth ──────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str
    portal: Optional[str] = None  # 'platform', 'company', 'app' (inferred if None)


class MasterAdminOut(BaseModel):
    id: int
    name: str
    email: str
    role: str = "MASTER_ADMIN"
    portal: str = "platform"
    status: str = "active"
    permissions: List[str] = ["platform.manage"]

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = "bearer"
    user: Optional[Union["UserOut", MasterAdminOut, dict]] = None
    portal: Optional[str] = None
    must_change_password: Optional[bool] = False
    mfa_required: Optional[bool] = False
    mfa_pending_token: Optional[str] = None
    mfa_enrollment_required: Optional[bool] = False
    mfa_enrollment_token: Optional[str] = None


# ── MFA Schemas (Module 6) ───────────────────────────────────────────────────

class MfaEnrollStartResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_code_svg: str
    qr_code_data_url: Optional[str] = None


class MfaEnrollVerifyRequest(BaseModel):
    code: str
    enrollment_token: Optional[str] = None


class MfaEnrollVerifyResponse(BaseModel):
    message: str
    recovery_codes: List[str]
    access_token: Optional[str] = None
    portal: Optional[str] = None
    user: Optional[Union["UserOut", MasterAdminOut, dict]] = None


class MfaVerifyRequest(BaseModel):
    mfa_pending_token: str
    code: str


class MfaRecoveryVerifyRequest(BaseModel):
    mfa_pending_token: str
    recovery_code: str


class MfaStatusResponse(BaseModel):
    enabled: bool
    mandatory: bool
    remaining_recovery_codes: int
    enabled_at: Optional[datetime] = None


class MfaDisableRequest(BaseModel):
    password: str
    code: str


class MfaRegenerateRecoveryRequest(BaseModel):
    code: Optional[str] = None
    password: Optional[str] = None


class MfaRegenerateRecoveryResponse(BaseModel):
    message: str
    recovery_codes: List[str]


class CompanyMfaPolicyRequest(BaseModel):
    mfa_required_for_all: bool


class CompanyMfaPolicyResponse(BaseModel):
    company_id: int
    mfa_required_for_all: bool


class PlatformMfaPolicyRequest(BaseModel):
    enforce_master_admin: Optional[bool] = None
    enforce_company_admin: Optional[bool] = None
    enforce_all: Optional[bool] = None


class PlatformMfaPolicyResponse(BaseModel):
    enforce_master_admin: bool
    enforce_company_admin: bool
    enforce_all: bool


class InviteRequest(BaseModel):
    email: str
    branch_id: int
    invited_role: UserRole


class InviteAcceptRequest(BaseModel):
    token: str
    name: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str
    portal: Optional[str] = "app"


class PasswordResetSubmit(BaseModel):
    token: str
    new_password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class GenericMessageResponse(BaseModel):
    message: str



# ── Company & Branch ──────────────────────────────────────────────────────────

class CompanyOut(BaseModel):
    id: int
    name: str
    code: str
    status: CompanyStatus
    gstin: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BranchOut(BaseModel):
    id: int
    company_id: int
    name: str
    code: str
    branch_type: Optional[str] = "Branch"
    branch_email: Optional[str] = None
    branch_contact_number: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = "India"
    gst_registered: Optional[bool] = False
    gstin: Optional[str] = None
    gst_type: Optional[str] = None
    status: Optional[str] = "active"
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateBranchRequest(BaseModel):
    # Section 1: Branch Details
    branch_name: str
    branch_code: str
    branch_type: str = "Branch"
    branch_email: Optional[str] = None
    branch_contact_number: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    district: str
    state: str
    pincode: str
    country: Optional[str] = "India"
    gst_registered: bool = False
    gstin: Optional[str] = None
    gst_type: Optional[str] = None

    # Section 2: Primary Admin User
    admin_name: str
    admin_email: str
    admin_mobile: str


class PrimaryAdminSummary(BaseModel):
    id: Optional[int] = None
    name: str
    email: str
    mobile: Optional[str] = None
    status: str
    is_activated: bool


class BranchDetailOut(BaseModel):
    id: int
    company_id: int
    name: str
    code: str
    branch_type: Optional[str] = "Branch"
    branch_email: Optional[str] = None
    branch_contact_number: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = "India"
    gst_registered: Optional[bool] = False
    gstin: Optional[str] = None
    gst_type: Optional[str] = None
    status: Optional[str] = "active"
    created_at: datetime
    user_count: int = 0
    active_user_count: int = 0
    total_user_count: int = 0
    document_count: int = 0
    primary_admin: Optional[PrimaryAdminSummary] = None

    model_config = {"from_attributes": True}


class CreateBranchResponse(BaseModel):
    message: str
    branch: BranchDetailOut
    activation_url: Optional[str] = None



# ── User ──────────────────────────────────────────────────────────────────────

class UserRoleAssignmentOut(BaseModel):
    id: Optional[int] = None
    role: str
    scope_type: str
    scope_id: int

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    company_id: int
    company_name: str
    company_display_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    branch_id: int
    branch_name: str
    branch_code: str
    permissions: List[str] = []
    assignments: List[UserRoleAssignmentOut] = []

    # Backward compatibility fields (synced with branch)
    tenant_id: int
    tenant_name: str

    model_config = {"from_attributes": True}


# ── Document ──────────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    file_size: int
    ocr_status: OcrStatus
    ocr_text: Optional[str] = None
    sha256: Optional[str] = None
    page_count: Optional[int] = None
    error_code: Optional[str] = None
    created_at: datetime
    uploaded_by: int
    uploader_name: str
    company_id: int
    branch_id: int
    branch_name: Optional[str] = ""
    template_version_id: Optional[int] = None
    deleted_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    restored_by: Optional[int] = None

    # Module 12 Search Fields
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    vendor_name: Optional[str] = None
    seller_name: Optional[str] = None
    seller_gstin: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_gstin: Optional[str] = None
    invoice_amount: Optional[float] = None
    grand_total: Optional[float] = None
    currency: Optional[str] = "INR"
    snippet: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_url: Optional[str] = None

    # Backward compatibility
    tenant_id: int

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    file_size: int
    ocr_status: OcrStatus
    sha256: Optional[str] = None
    page_count: Optional[int] = None
    error_code: Optional[str] = None
    created_at: datetime
    uploaded_by: int
    uploader_name: str
    company_id: int
    branch_id: int
    branch_name: Optional[str] = ""
    template_version_id: Optional[int] = None
    deleted_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    restored_by: Optional[int] = None

    # Module 12 Search Fields
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    vendor_name: Optional[str] = None
    seller_name: Optional[str] = None
    seller_gstin: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_gstin: Optional[str] = None
    invoice_amount: Optional[float] = None
    grand_total: Optional[float] = None
    currency: Optional[str] = "INR"
    snippet: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_url: Optional[str] = None

    # Backward compatibility
    tenant_id: int

    model_config = {"from_attributes": True}


class SearchResultItem(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    file_size: int
    ocr_status: str
    page_count: Optional[int] = None
    created_at: Optional[str] = None
    uploaded_by: int
    uploader_name: str
    company_id: int
    branch_id: int
    branch_name: Optional[str] = ""
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    vendor_name: Optional[str] = None
    seller_name: Optional[str] = None
    seller_gstin: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_gstin: Optional[str] = None
    invoice_amount: Optional[float] = None
    grand_total: Optional[float] = None
    currency: Optional[str] = "INR"
    snippet: Optional[str] = None
    thumbnail_url: str
    file_url: str

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    items: List[SearchResultItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    query: Optional[str] = None
    filters: Dict[str, Any] = {}


class FileUploadResultItem(BaseModel):
    filename: str
    status: str  # "success" or "error"
    document: Optional[DocumentOut] = None
    error_code: Optional[str] = None
    error: Optional[str] = None


class BatchUploadResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: List[FileUploadResultItem]


class PaginatedDocumentResponse(BaseModel):
    items: List[DocumentListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Invoice ───────────────────────────────────────────────────────────────────

class InvoiceOut(BaseModel):
    id: int
    document_id: Optional[int] = None
    original_filename: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    seller_name: Optional[str] = None
    seller_gstin: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_gstin: Optional[str] = None
    grand_total: Optional[str] = None
    currency: Optional[str] = "INR"
    pdf_filename: Optional[str] = None
    file_size: Optional[int] = 0
    created_at: Optional[datetime] = None
    uploaded_by: Optional[int] = None
    uploader_name: Optional[str] = None
    company_id: int
    company_name: Optional[str] = None
    branch_id: int
    branch_name: Optional[str] = None
    kind: Optional[str] = "copy"
    status: Optional[str] = "available"
    taxable_amount: Optional[str] = None
    cgst_amount: Optional[str] = None
    sgst_amount: Optional[str] = None
    igst_amount: Optional[str] = None
    round_off: Optional[str] = None

    # Backward compatibility
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Company Onboarding Schemas ───────────────────────────────────────────────

class CompanyOnboardingInitiate(BaseModel):
    company_name: str
    contact_name: str
    contact_email: str


class CompanyOnboardingSubmit(BaseModel):
    # Section A
    legal_company_name: str
    trade_name: Optional[str] = None
    business_type: str
    business_description: Optional[str] = None
    year_of_establishment: Optional[str] = None
    company_website: Optional[str] = None

    # Section B
    pan_number: str
    gstin: Optional[str] = None
    gst_type: Optional[str] = None
    cin: Optional[str] = None
    llpin: Optional[str] = None
    udyam_number: Optional[str] = None
    tan: Optional[str] = None

    # Section C
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    district: str
    pincode: str
    country: Optional[str] = "India"

    # Section D
    auth_contact_name: str
    auth_contact_designation: str
    auth_contact_email: str
    auth_contact_mobile: str
    auth_contact_alternate_mobile: Optional[str] = None

    # Section E
    has_multiple_branches: bool = False
    branch_details: Optional[List[Any]] = []

    # Section F
    admin_name: str
    admin_email: str
    admin_password: Optional[str] = None
    confirm_password: Optional[str] = None
    admin_mobile: str
    admin_designation: str

    # Section G
    primary_document_types: Optional[List[str]] = []
    expected_monthly_volume: Optional[str] = None
    languages: Optional[List[str]] = []
    timezone: Optional[str] = "Asia/Kolkata"
    currency: Optional[str] = "INR"


class RequestChangesPayload(BaseModel):
    comments: str


class RejectPayload(BaseModel):
    reason: Optional[str] = "Application does not meet onboarding criteria."


class CompanyOnboardingListItem(BaseModel):
    id: int
    token: str
    status: OnboardingStatus
    initial_company_name: str
    contact_name: str
    contact_email: str
    legal_company_name: Optional[str] = None
    auth_contact_mobile: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_comments: Optional[str] = None

    model_config = {"from_attributes": True}


class CompanyOnboardingOut(BaseModel):
    id: int
    token: str
    status: OnboardingStatus
    initial_company_name: str
    contact_name: str
    contact_email: str
    onboarding_url: Optional[str] = None

    # Section A
    legal_company_name: Optional[str] = None
    trade_name: Optional[str] = None
    business_type: Optional[str] = None
    business_description: Optional[str] = None
    year_of_establishment: Optional[str] = None
    company_website: Optional[str] = None

    # Section B
    pan_number: Optional[str] = None
    gstin: Optional[str] = None
    gst_type: Optional[str] = None
    cin: Optional[str] = None
    llpin: Optional[str] = None
    udyam_number: Optional[str] = None
    tan: Optional[str] = None

    # Section C
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = "India"

    # Section D
    auth_contact_name: Optional[str] = None
    auth_contact_designation: Optional[str] = None
    auth_contact_email: Optional[str] = None
    auth_contact_mobile: Optional[str] = None
    auth_contact_alternate_mobile: Optional[str] = None

    # Section E
    has_multiple_branches: Optional[bool] = False
    branch_details: Optional[List[Any]] = []

    # Section F
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_mobile: Optional[str] = None
    admin_designation: Optional[str] = None
    has_admin_password: Optional[bool] = False

    # Section G
    primary_document_types: Optional[List[str]] = []
    expected_monthly_volume: Optional[str] = None
    languages: Optional[List[str]] = []
    timezone: Optional[str] = "Asia/Kolkata"
    currency: Optional[str] = "INR"

    # Documents & Reviews
    uploaded_documents: Optional[Dict[str, Any]] = {}
    review_comments: Optional[str] = None
    review_history: Optional[List[Dict[str, Any]]] = []
    company_id: Optional[int] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Audit Log Schemas (Module 5) ─────────────────────────────────────────────

class AuditLogOut(BaseModel):
    id: int
    occurred_at: datetime
    actor_type: str
    actor_id: Optional[int] = None
    company_id: Optional[int] = None
    branch_id: Optional[int] = None
    action: str
    object_type: Optional[str] = None
    object_id: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("event_metadata", "metadata", "metadata_"),
    )

    model_config = {"from_attributes": True, "populate_by_name": True}


class AuditLogPaginationResponse(BaseModel):
    items: List[AuditLogOut]
    total: int
    page: int
    page_size: int
    pages: int
    total_count: Optional[int] = None
    total_pages: Optional[int] = None


# ── Module 7 Management, Quotas & Dashboard Schemas ──────────────────────────

class CompanyUpdatePayload(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None
    mfa_required_for_all: Optional[bool] = None
    max_branches: Optional[int] = Field(None, ge=1)
    max_users: Optional[int] = Field(None, ge=1)
    storage_limit_bytes: Optional[int] = Field(None, ge=0)
    monthly_ai_budget_cents: Optional[int] = Field(None, ge=0)


class CompanyDetailOut(BaseModel):
    id: int
    name: str
    code: str
    status: str
    display_name: Optional[str] = None
    logo_url: Optional[str] = None
    pan: Optional[str] = None
    pan_number: Optional[str] = None
    gstin: Optional[str] = None
    website: Optional[str] = None
    company_website: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    registered_address: Optional[str] = None
    mfa_required_for_all: bool
    max_branches: int
    max_users: int
    storage_limit_bytes: int
    monthly_ai_budget_cents: int
    ai_budget_spent_cents: int
    monthly_ai_budget_inr: Optional[float] = None
    ai_budget_spent_inr: Optional[float] = None
    reporting_currency: Optional[str] = "INR"
    branch_count: int
    user_count: int
    document_count: int
    storage_used_bytes: int
    ai_spent_cents: int
    created_at: datetime
    updated_at: datetime
    onboarding_id: Optional[int] = None

    model_config = {"from_attributes": True}


class DashboardStatsOut(BaseModel):
    total_companies: int
    active_companies: int
    suspended_companies: int
    total_branches: int
    total_users: int
    total_documents: int
    total_storage_bytes: int
    total_ai_spent_cents: int
    total_ai_spent_inr: Optional[float] = None
    exchange_rate: Optional[float] = 85.0
    pending_onboardings: int
    recent_activity: List[Dict[str, Any]] = []


class SystemSettingsOut(BaseModel):
    system_defaults: Dict[str, Any]
    ai_providers: Dict[str, Any]
    mfa_policy: Dict[str, Any]


class SystemSettingsUpdatePayload(BaseModel):
    system_defaults: Optional[Dict[str, Any]] = None
    ai_providers: Optional[Dict[str, Any]] = None
    apply_to_existing_companies: Optional[bool] = False


# ── Module 8: Company Admin Portal Schemas ─────────────────────────────────────

class CompanyProfileOut(BaseModel):
    id: int
    name: str
    code: str
    display_name: Optional[str] = None
    trade_name: Optional[str] = None
    logo_url: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    pan_number: Optional[str] = None
    address: Optional[str] = None
    registered_address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_name: Optional[str] = None
    auth_contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    auth_contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    auth_contact_mobile: Optional[str] = None
    website: Optional[str] = None
    company_website: Optional[str] = None
    status: str
    mfa_required_for_all: bool
    max_branches: int
    max_users: int
    storage_limit_bytes: int
    monthly_ai_budget_cents: int
    ai_budget_spent_cents: int
    monthly_ai_budget_inr: Optional[float] = None
    ai_budget_spent_inr: Optional[float] = None
    reporting_currency: Optional[str] = "INR"
    branch_count: int
    user_count: int
    document_count: int
    storage_used_bytes: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CompanyProfileUpdate(BaseModel):
    name: Optional[str] = None
    legal_company_name: Optional[str] = None
    display_name: Optional[str] = None
    trade_name: Optional[str] = None
    logo_url: Optional[str] = None
    contact_person: Optional[str] = None
    contact_name: Optional[str] = None
    auth_contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    auth_contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    auth_contact_mobile: Optional[str] = None
    website: Optional[str] = None
    company_website: Optional[str] = None
    address: Optional[str] = None
    registered_address: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    pan_number: Optional[str] = None


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    branch_type: Optional[str] = None
    branch_email: Optional[str] = None
    branch_contact_number: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = None
    gst_registered: Optional[bool] = None
    gstin: Optional[str] = None
    gst_type: Optional[str] = None


class CompanyUserItem(BaseModel):
    id: int
    name: str
    email: str
    mobile: Optional[str] = None
    role: str
    status: str
    branch_id: int
    branch_name: str
    primary_branch_id: Optional[int] = None
    primary_branch_name: Optional[str] = None
    assigned_branches: List[Dict[str, Any]] = []
    mfa_enabled: bool = False
    token_version: int = 1
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class CompanyUsersPaginationResponse(BaseModel):
    items: List[CompanyUserItem]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class CompanyUserInviteRequest(BaseModel):
    name: str
    email: str
    mobile: Optional[str] = None
    role: str
    branch_id: int
    primary_branch_id: Optional[int] = None
    additional_branch_ids: Optional[List[int]] = None


class CompanyUserUpdateRequest(BaseModel):
    name: Optional[str] = None
    mobile: Optional[str] = None
    role: Optional[str] = None
    branch_id: Optional[int] = None
    primary_branch_id: Optional[int] = None
    additional_branch_ids: Optional[List[int]] = None


class CompanyInvitationItem(BaseModel):
    id: int
    email: str
    branch_id: int
    branch_name: str
    branch_code: Optional[str] = None
    invited_role: str
    role: Optional[str] = None
    invited_by_name: Optional[str] = None
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    status: str
    accepted: bool = False
    revoked: bool = False
    is_valid: bool = False
    created_at: datetime


# ── Module 13: GST Registrations ──────────────────────────────────────────────

class GstRegistrationCreate(BaseModel):
    gstin: str
    legal_name: str
    trade_name: Optional[str] = None
    state_code: Optional[str] = None
    state_name: Optional[str] = None
    registered_address: Optional[str] = None
    is_default: bool = False


class GstRegistrationUpdate(BaseModel):
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    registered_address: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class GstRegistrationOut(BaseModel):
    id: int
    company_id: int
    gstin: str
    legal_name: str
    trade_name: Optional[str] = None
    state_code: str
    state_name: str
    registered_address: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Module 13: Customers & Addresses ─────────────────────────────────────────

class CustomerAddressCreate(BaseModel):
    address_type: str = "billing"  # billing | shipping
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state_code: str
    state_name: str
    pincode: str
    is_default: bool = False


class CustomerAddressOut(BaseModel):
    id: int
    customer_id: int
    address_type: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state_code: str
    state_name: str
    pincode: str
    is_default: bool = False

    model_config = {"from_attributes": True}


class CustomerCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_b2c: bool = False
    billing_address: Optional[CustomerAddressCreate] = None
    shipping_address: Optional[CustomerAddressCreate] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_b2c: Optional[bool] = None
    is_active: Optional[bool] = None


class CustomerOut(BaseModel):
    id: int
    company_id: int
    name: str
    display_name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_b2c: bool = False
    is_active: bool = True
    addresses: List[CustomerAddressOut] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Module 13: Outbound Sales Invoices & Line Items ──────────────────────────

class InvoiceItemInput(BaseModel):
    description: str
    hsn_sac_code: Optional[str] = None
    item_type: str = "goods"  # goods | services
    quantity: Decimal
    unit: str = "nos"
    unit_price: Decimal
    discount_percent: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    gst_rate: Decimal = Decimal("18.00")
    gst_classification: str = "TAXABLE"


class InvoiceItemOut(BaseModel):
    id: Optional[int] = None
    item_order: int
    description: str
    hsn_sac_code: Optional[str] = None
    item_type: str = "goods"
    quantity: Decimal
    unit: str = "nos"
    unit_price: Decimal
    gross_amount: Decimal
    discount_percent: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    taxable_amount: Decimal
    gst_classification: str = "TAXABLE"
    gst_rate: Decimal
    cgst_rate: Decimal = Decimal("0.00")
    cgst_amount: Decimal = Decimal("0.00")
    sgst_rate: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_rate: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")
    total_tax_amount: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class SignatureLayoutInput(BaseModel):
    id: Optional[int] = None
    upload_token: Optional[str] = None
    page_number: int = 1
    is_pinned_to_last_page: bool = False
    x_mm: Decimal
    y_mm: Decimal
    width_mm: Decimal
    height_mm: Decimal


class SignatureLayoutOut(BaseModel):
    id: int
    invoice_id: int
    storage_key: str
    original_filename: str
    mime_type: str
    file_size: int
    sha256: str
    page_number: int
    is_pinned_to_last_page: bool
    x_mm: Decimal
    y_mm: Decimal
    width_mm: Decimal
    height_mm: Decimal
    image_url: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemporarySignatureUploadOut(BaseModel):
    upload_token: str
    temp_view_url: str
    aspect_ratio: Decimal
    width_px: int
    height_px: int
    default_width_mm: Decimal
    default_height_mm: Decimal


class SalesInvoiceDraftCreate(BaseModel):
    branch_id: int
    gst_registration_id: int
    customer_id: int
    billing_address_id: Optional[int] = None
    shipping_address_id: Optional[int] = None
    place_of_supply: str  # 2-digit state code, e.g. "33"
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    apply_round_off: bool = False
    series_code: str = "INV"
    items: List[InvoiceItemInput] = []
    signatures: Optional[List[SignatureLayoutInput]] = None


class SalesInvoiceDraftUpdate(BaseModel):
    branch_id: Optional[int] = None
    customer_id: Optional[int] = None
    gst_registration_id: Optional[int] = None
    billing_address_id: Optional[int] = None
    shipping_address_id: Optional[int] = None
    place_of_supply: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    apply_round_off: Optional[bool] = None
    series_code: Optional[str] = None
    items: Optional[List[InvoiceItemInput]] = None
    signatures: Optional[List[SignatureLayoutInput]] = None


class SalesInvoiceApprovalInput(BaseModel):
    notes: Optional[str] = None


class SalesInvoiceCancelInput(BaseModel):
    reason: str


class SalesInvoiceOut(BaseModel):
    id: int
    company_id: int
    branch_id: int
    branch_name: Optional[str] = None
    kind: str = "generated"
    status: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    financial_year: Optional[str] = None
    customer_id: int
    customer_name: str
    customer_gstin: Optional[str] = None
    is_b2c: bool = False
    gst_registration_id: int
    supplier_gstin: str
    supplier_legal_name: str
    place_of_supply: str
    place_of_supply_state_name: Optional[str] = None
    billing_address: Optional[Dict[str, Any]] = None
    shipping_address: Optional[Dict[str, Any]] = None
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    round_off: Decimal
    grand_total: Decimal
    currency: str = "INR"
    notes: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    pdf_filename: Optional[str] = None
    pdf_sha256: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    approved_by: Optional[int] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    issued_at: Optional[datetime] = None
    items: List[InvoiceItemOut] = []
    signatures: List[SignatureLayoutOut] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaxPreviewRequest(BaseModel):
    supplier_state_code: str
    place_of_supply: str
    items: List[InvoiceItemInput]
    apply_round_off: bool = False


class TaxPreviewResponse(BaseModel):
    supplier_state_code: str
    place_of_supply: str
    is_intra_state: bool
    apply_round_off: bool
    lines: List[InvoiceItemOut]
    total_gross_amount: Decimal
    total_discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax_amount: Decimal
    round_off: Decimal
    grand_total: Decimal


class UnifiedInvoiceOut(BaseModel):
    id: int
    company_id: int
    branch_id: int
    branch_name: Optional[str] = None
    kind: str  # copy | generated
    status: str  # available, stale, superseded, draft, pending_approval, approved, cancelled
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    seller_name: Optional[str] = None
    seller_gstin: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_gstin: Optional[str] = None
    taxable_amount: Optional[Decimal] = None
    cgst_amount: Optional[Decimal] = None
    sgst_amount: Optional[Decimal] = None
    igst_amount: Optional[Decimal] = None
    round_off: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None
    currency: str = "INR"
    document_id: Optional[int] = None
    pdf_filename: Optional[str] = None
    copy_version: Optional[int] = None
    is_current: Optional[bool] = None
    is_stale: Optional[bool] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class InvoiceListPaginationResponse(BaseModel):
    items: List[UnifiedInvoiceOut]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    stats: Optional[Dict[str, Any]] = None


class InvoiceStatsOut(BaseModel):
    total_count: int
    copies_count: int
    generated_count: int
    draft_count: int
    pending_approval_count: int
    approved_count: int
    cancelled_count: int
    total_approved_amount: Decimal


# Forward ref resolution
TokenResponse.model_rebuild()

