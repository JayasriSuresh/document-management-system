import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Enum,
    ForeignKey,
    BigInteger,
    Text,
    JSON,
    UniqueConstraint,
    ForeignKeyConstraint,
    Index,
    Boolean,
    CheckConstraint,
    Date,
    Numeric,
    text,
    and_,
)
from sqlalchemy.orm import relationship, synonym, foreign
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from app.database import Base


class UserRole(str, enum.Enum):
    GLOBAL_ADMIN = "GLOBAL_ADMIN"
    ADMIN = "ADMIN"
    STAFF = "STAFF"
    UPLOADER = "UPLOADER"


class OcrStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CompanyStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"


class OnboardingStatus(str, enum.Enum):
    PENDING_SUBMISSION = "pending_submission"
    SUBMITTED = "submitted"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"


# ── Company (Primary Tenant Boundary) ─────────────────────────────────────────

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(
        Enum(CompanyStatus, name="companystatus", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=CompanyStatus.ACTIVE,
    )
    gstin = Column(String(32), nullable=True)
    pan = Column(String(32), nullable=True)
    display_name = Column(String(255), nullable=True)
    logo_url = Column(Text, nullable=True)
    contact_person = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(32), nullable=True)
    website = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    limits = Column(JSON, nullable=True, default=dict)
    mfa_required_for_all = Column(Boolean, nullable=False, default=False)
    allow_branch_mfa_control = Column(Boolean, nullable=False, default=False)

    # ── Quotas & Resource Allocation ──────────────────────────────────────────
    max_branches = Column(Integer, nullable=False, default=5)
    max_users = Column(Integer, nullable=False, default=20)
    storage_limit_bytes = Column(BigInteger, nullable=False, default=5368709120)  # 5 GB
    monthly_ai_budget_cents = Column(Integer, nullable=False, default=2500)      # $25.00
    ai_budget_spent_cents = Column(Integer, nullable=False, default=0)
    monthly_ai_budget_inr = Column(Numeric(12, 2), nullable=True)
    ai_budget_spent_inr = Column(Numeric(12, 4), nullable=False, default=0.0)
    reporting_currency = Column(String(10), nullable=False, default="INR")

    # ── Approval Policy ───────────────────────────────────────────────────────
    invoice_approval_policy = Column(String(50), nullable=False, default="admin_only")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    branches = relationship("Branch", back_populates="company", cascade="all, delete-orphan")
    users = relationship("User", back_populates="company", overlaps="branch")
    documents = relationship("Document", back_populates="company", overlaps="branch")
    invoices = relationship("Invoice", back_populates="company", overlaps="branch")
    gst_registrations = relationship("GstRegistration", back_populates="company", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="company", cascade="all, delete-orphan")
    expense_categories = relationship("ExpenseCategory", back_populates="company", cascade="all, delete-orphan")
    number_sequences = relationship("NumberSequence", back_populates="company", cascade="all, delete-orphan")


# ── Branch (Subdivision within a Company) ─────────────────────────────────────

class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_branches_company_id"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=False)

    # ── Branch Details & Contact ──────────────────────────────────────────────
    branch_type = Column(String(100), nullable=True, default="Branch")  # Head Office, Regional Office, Branch, Warehouse, etc.
    branch_email = Column(String(255), nullable=True)
    branch_contact_number = Column(String(32), nullable=True)

    # ── Address ───────────────────────────────────────────────────────────────
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True, default="India")

    # ── Branch-specific GST details ───────────────────────────────────────────
    gst_registered = Column(Boolean, nullable=True, default=False)
    gstin = Column(String(32), nullable=True)
    gst_type = Column(String(64), nullable=True)
    gst_registration_id = Column(Integer, nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────
    status = Column(String(32), nullable=True, default="active")
    mfa_required_for_all = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_branches_company_id_id"),
        UniqueConstraint("company_id", "code", name="uq_branches_company_id_code"),
        ForeignKeyConstraint(
            ["company_id", "gst_registration_id"],
            ["gst_registrations.company_id", "gst_registrations.id"],
            name="fk_branches_gst_reg_tenant",
            ondelete="SET NULL",
        ),
    )

    company = relationship("Company", back_populates="branches")
    gst_registration = relationship("GstRegistration", back_populates="branches", foreign_keys=[gst_registration_id])
    users = relationship("User", back_populates="branch", overlaps="company,users")
    documents = relationship("Document", back_populates="branch", overlaps="company,documents")
    invoices = relationship("Invoice", back_populates="branch", overlaps="company,invoices")


# Alias for backward compatibility with existing code referring to Tenant
Tenant = Branch


# ── Master Admin (Platform-Level Identity) ───────────────────────────────────

class MasterAdmin(Base):
    __tablename__ = "master_admins"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(
        Enum(AccountStatus, name="accountstatus", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )
    token_version = Column(Integer, nullable=False, default=1)
    must_change_password = Column(Boolean, nullable=False, default=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    sessions = relationship("UserSession", back_populates="master_admin", cascade="all, delete-orphan")


# ── User ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_users_company_id"),
        nullable=False,
        index=True,
    )
    branch_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    mobile = Column(String(32), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole, name="userrole"), nullable=False, default=UserRole.STAFF)
    status = Column(
        Enum(AccountStatus, name="accountstatus", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )
    token_version = Column(Integer, nullable=False, default=1)
    must_change_password = Column(Boolean, nullable=False, default=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_users_company_branch",
            ondelete="CASCADE",
        ),
        Index("ix_users_company_branch", "company_id", "branch_id"),
    )

    company = relationship("Company", back_populates="users", overlaps="branch,users")
    branch = relationship("Branch", foreign_keys=[branch_id], back_populates="users", overlaps="company,users")
    documents = relationship("Document", foreign_keys="Document.uploaded_by", back_populates="uploader")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    role_assignments = relationship("UserRoleAssignment", foreign_keys="UserRoleAssignment.user_id", back_populates="user", cascade="all, delete-orphan")

    # Backward compatibility properties for existing code referencing tenant / tenant_id
    @property
    def tenant_id(self) -> int:
        return self.branch_id

    @tenant_id.setter
    def tenant_id(self, val: int) -> None:
        self.branch_id = val

    @property
    def tenant(self) -> Branch:
        return self.branch

    @tenant.setter
    def tenant(self, val: Branch) -> None:
        self.branch = val




# ── User Role Assignment (Module 4 Permissions & Scopes) ─────────────────────

class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_role_assignments_user_id"),
        nullable=False,
        index=True,
    )
    role = Column(String(64), nullable=False, index=True)
    scope_type = Column(String(32), nullable=False, index=True)  # "company" or "branch"
    scope_id = Column(Integer, nullable=False, index=True)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_role_assignments_created_by"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "role", "scope_type", "scope_id", name="uq_user_role_scope"),
        CheckConstraint("scope_type IN ('company', 'branch')", name="chk_role_assignment_scope_type"),
        Index("ix_user_role_assignments_user_role", "user_id", "role"),
        Index("ix_user_role_assignments_scope", "scope_type", "scope_id"),
    )

    user = relationship("User", foreign_keys=[user_id], back_populates="role_assignments")
    creator = relationship("User", foreign_keys=[created_by])


# ── Document ──────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_documents_company_id"),
        nullable=False,
        index=True,
    )
    branch_id = Column(Integer, nullable=False, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_filename = Column(String(512), nullable=False)
    storage_key = Column(String(512), nullable=False, unique=True)
    mime_type = Column(String(128), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    ocr_text = Column(Text, nullable=True)
    structured_data = Column(Text, nullable=True)
    ocr_status = Column(Enum(OcrStatus, name="ocrstatus"), nullable=False, default=OcrStatus.UPLOADED)
    sha256 = Column(String(64), nullable=True, index=True)
    page_count = Column(Integer, nullable=True)
    error_code = Column(String(64), nullable=True)
    template_version_id = Column(
        Integer,
        ForeignKey("template_versions.id", ondelete="SET NULL", name="fk_documents_template_version_id"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    restored_at = Column(DateTime, nullable=True)
    restored_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Module 12 Search & Structured Metadata Columns
    invoice_number = Column(String(128), nullable=True, index=True)
    invoice_date = Column(Date, nullable=True, index=True)
    seller_name = Column(String(255), nullable=True, index=True)
    seller_gstin = Column(String(32), nullable=True, index=True)
    buyer_name = Column(String(255), nullable=True, index=True)
    buyer_gstin = Column(String(32), nullable=True, index=True)
    grand_total = Column(Numeric(15, 2), nullable=True, index=True)
    currency = Column(String(10), nullable=True, default="INR")
    search_vector = Column(TSVECTOR, nullable=True)

    # Module 13 Expense Category
    category_id = Column(Integer, ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True)
    invoice_type = Column(String(64), nullable=True, default="Tax Invoice", index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_documents_company_branch",
            ondelete="CASCADE",
        ),
        UniqueConstraint("company_id", "id", name="uq_documents_company_id"),
        Index("ix_documents_company_branch", "company_id", "branch_id"),
        Index("ix_documents_company_created", "company_id", "created_at"),
        Index("ix_documents_company_branch_created", "company_id", "branch_id", "created_at"),
        Index("ix_documents_company_grand_total", "company_id", "grand_total"),
        Index("ix_documents_company_invoice_date", "company_id", "invoice_date"),
        Index("ix_documents_company_status", "company_id", "ocr_status"),
        Index("ix_documents_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_documents_company_sha256_active",
            "company_id",
            "sha256",
            postgresql_where=text("deleted_at IS NULL AND sha256 IS NOT NULL"),
        ),
    )

    company = relationship("Company", back_populates="documents", overlaps="branch,documents")
    branch = relationship("Branch", foreign_keys=[branch_id], back_populates="documents", overlaps="company,documents")
    uploader = relationship("User", foreign_keys=[uploaded_by], back_populates="documents")
    deleter = relationship("User", foreign_keys=[deleted_by])
    restorer = relationship("User", foreign_keys=[restored_by])
    processing_jobs = relationship("ProcessingJob", back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    invoice_record = relationship("Invoice", back_populates="document", cascade="all, delete-orphan", passive_deletes=True, uselist=False)
    template_version = relationship("TemplateVersion", foreign_keys=[template_version_id])
    extraction = relationship("DocumentExtraction", back_populates="document", cascade="all, delete-orphan", uselist=False)
    expense_category = relationship("ExpenseCategory", back_populates="documents")
    supplier_copies = relationship(
        "SupplierInvoiceCopy",
        back_populates="document",
        primaryjoin="and_(Document.company_id == SupplierInvoiceCopy.company_id, Document.id == SupplierInvoiceCopy.document_id)"
    )

    # Backward compatibility properties
    @property
    def tenant_id(self) -> int:
        return self.branch_id

    @tenant_id.setter
    def tenant_id(self, val: int) -> None:
        self.branch_id = val

    @property
    def tenant(self) -> Branch:
        return self.branch

    @tenant.setter
    def tenant(self, val: Branch) -> None:
        self.branch = val




# ── Invoice ───────────────────────────────────────────────────────────────────

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT", name="fk_invoices_company_id"),
        nullable=False,
        index=True,
    )
    branch_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="copy")
    status = Column(String(30), nullable=False, default="available")

    # Financial & Statutory fields (Pure Decimal & Date)
    invoice_number = Column(String(100), nullable=True, index=True)
    invoice_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    taxable_amount = Column(Numeric(15, 2), nullable=True)
    cgst_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    sgst_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    igst_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    round_off = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    grand_total = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(32), default="INR")
    notes = Column(Text, nullable=True)
    invoice_type = Column(String(64), nullable=True, default="Tax Invoice", index=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

    # Legacy compatibility columns
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    gst_registration_id = Column(Integer, nullable=True, index=True)
    seller_name = Column(String(512), nullable=True)
    seller_gstin = Column(String(255), nullable=True)
    buyer_name = Column(String(512), nullable=True)
    buyer_gstin = Column(String(255), nullable=True)
    pdf_filename = Column(String(512), nullable=True)
    file_size = Column(BigInteger, nullable=True, default=0)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_invoices_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "gst_registration_id"],
            ["gst_registrations.company_id", "gst_registrations.id"],
            name="fk_invoices_gst_registration",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("company_id", "id", name="uq_invoices_company_id"),
        UniqueConstraint("company_id", "id", "gst_registration_id", name="uq_invoices_comp_id_gst"),
        CheckConstraint(
            "kind != 'generated' OR gst_registration_id IS NOT NULL",
            name="chk_invoices_gst_registration_requirement",
        ),
        Index("ix_invoices_company_branch", "company_id", "branch_id"),
        Index("ix_invoices_company_created", "company_id", "created_at"),
    )

    document = relationship("Document", back_populates="invoice_record")
    company = relationship("Company", back_populates="invoices", overlaps="branch,invoices")
    branch = relationship("Branch", foreign_keys=[branch_id], overlaps="company,invoices")
    gst_registration = relationship(
        "GstRegistration",
        foreign_keys=[gst_registration_id],
        primaryjoin="and_(Invoice.company_id == GstRegistration.company_id, Invoice.gst_registration_id == GstRegistration.id)",
        overlaps="company,branches,gst_registrations",
    )
    creator = relationship("User", foreign_keys=[created_by])
    uploader = relationship("User", foreign_keys=[uploaded_by])

    supplier_copy = relationship(
        "SupplierInvoiceCopy",
        back_populates="invoice",
        uselist=False,
        cascade="all, delete-orphan",
        primaryjoin="and_(Invoice.company_id == SupplierInvoiceCopy.company_id, Invoice.id == SupplierInvoiceCopy.invoice_id)",
        overlaps="document,supplier_copies",
    )
    sales_detail = relationship(
        "OutboundSalesInvoice",
        back_populates="invoice",
        uselist=False,
        cascade="all, delete-orphan",
        primaryjoin="and_(Invoice.company_id == OutboundSalesInvoice.company_id, Invoice.id == OutboundSalesInvoice.invoice_id)",
        overlaps="customer,gst_registration,sales_invoices",
    )
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.line_number")
    signatures = relationship(
        "SalesInvoiceSignature",
        back_populates="invoice",
        cascade="all, delete-orphan",
        primaryjoin="and_(Invoice.company_id == SalesInvoiceSignature.company_id, Invoice.id == SalesInvoiceSignature.invoice_id)",
        order_by="SalesInvoiceSignature.id",
    )

    # Backward compatibility properties
    @property
    def tenant_id(self) -> int:
        return self.branch_id

    @tenant_id.setter
    def tenant_id(self, val: int) -> None:
        self.branch_id = val

    @property
    def tenant(self) -> Branch:
        return self.branch

    @tenant.setter
    def tenant(self, val: Branch) -> None:
        self.branch = val




    @property
    def financial_year(self):
        if self.sales_detail:
            return self.sales_detail.financial_year
        return None


# ── Module 13: Invoice Generation & Management Models ─────────────────────────

class GstRegistration(Base):
    __tablename__ = "gst_registrations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    gstin = Column(String(15), nullable=False, unique=True, index=True)
    legal_name = Column(String(255), nullable=False)
    trade_name = Column(String(255), nullable=True)
    name = synonym("legal_name")
    display_name = synonym("trade_name")
    state_code = Column(String(2), nullable=False)
    state_name = Column(String(100), nullable=False)
    registered_address = Column(Text, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_gst_reg_company_tenant"),
    )

    company = relationship("Company", back_populates="gst_registrations")
    branches = relationship(
        "Branch",
        back_populates="gst_registration",
        primaryjoin="and_(GstRegistration.company_id == Branch.company_id, GstRegistration.id == Branch.gst_registration_id)",
        overlaps="company,branches"
    )
    number_sequences = relationship("NumberSequence", back_populates="gst_registration", cascade="all, delete-orphan", overlaps="company,number_sequences")
    sales_invoices = relationship(
        "OutboundSalesInvoice",
        back_populates="gst_registration",
        primaryjoin="and_(GstRegistration.company_id == OutboundSalesInvoice.company_id, GstRegistration.id == OutboundSalesInvoice.gst_registration_id)",
        overlaps="customer,sales_detail,sales_invoices"
    )


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_code = Column(String(50), nullable=True)
    legal_name = Column(String(255), nullable=False)
    trade_name = Column(String(255), nullable=True)
    name = synonym("legal_name")
    display_name = synonym("trade_name")
    gstin = Column(String(15), nullable=True, index=True)
    pan = Column(String(10), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    is_b2c = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_customers_company_tenant"),
    )

    company = relationship("Company", back_populates="customers")
    addresses = relationship("CustomerAddress", back_populates="customer", cascade="all, delete-orphan")
    sales_invoices = relationship(
        "OutboundSalesInvoice",
        back_populates="customer",
        primaryjoin="and_(Customer.company_id == OutboundSalesInvoice.company_id, Customer.id == OutboundSalesInvoice.customer_id)",
        overlaps="gst_registration,sales_detail,sales_invoices"
    )


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    address_type = Column(String(20), nullable=False)  # 'billing', 'shipping', 'both'
    address_line1 = Column(String(255), nullable=False)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state_code = Column(String(2), nullable=False)
    state_name = Column(String(100), nullable=False)
    pincode = Column(String(20), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("customer_id", "id", name="uq_customer_address_tenant"),
    )

    customer = relationship("Customer", back_populates="addresses")


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_expense_cat_company_tenant"),
        UniqueConstraint("company_id", "code", name="uq_expense_cat_company_code"),
    )

    company = relationship("Company", back_populates="expense_categories")
    documents = relationship("Document", back_populates="expense_category")


class HsnSacRate(Base):
    __tablename__ = "hsn_sac_rates"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), nullable=False, index=True)
    description = Column(Text, nullable=False)
    item_type = Column(String(10), nullable=False)  # 'goods', 'services'
    gst_rate = Column(Numeric(5, 2), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("code", "item_type", "effective_from", name="uq_hsn_sac_timeline"),
    )


class NumberSequence(Base):
    __tablename__ = "number_sequences"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    gst_registration_id = Column(Integer, nullable=False, index=True)
    financial_year = Column(String(10), nullable=False)  # '2026-27'
    series_code = Column(String(20), nullable=False, default="INV")
    next_value = Column(Integer, nullable=False, default=1)
    padding = Column(Integer, nullable=False, default=4)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "gst_registration_id"],
            ["gst_registrations.company_id", "gst_registrations.id"],
            name="fk_sequence_gst_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "gst_registration_id", "financial_year", "series_code",
            name="uq_number_sequence_tenant"
        ),
    )

    company = relationship("Company", back_populates="number_sequences")
    gst_registration = relationship("GstRegistration", back_populates="number_sequences", overlaps="company,number_sequences")


class SupplierInvoiceCopy(Base):
    __tablename__ = "supplier_invoice_copies"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, nullable=False, index=True)
    company_id = Column(Integer, nullable=False, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    supplier_invoice_number = Column(String(100), nullable=True)
    supplier_name = Column(String(255), nullable=True)
    supplier_gstin = Column(String(15), nullable=True)
    copy_version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    is_stale = Column(Boolean, nullable=False, default=False)
    source_data_hash = Column(String(64), nullable=False)
    template_version_id = Column(Integer, nullable=True)
    pdf_storage_key = Column(String(500), nullable=False)
    pdf_sha256 = Column(String(64), nullable=False)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_copy_invoice_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "document_id"],
            ["documents.company_id", "documents.id"],
            name="fk_copy_document_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("document_id", "copy_version", name="uq_copy_version_per_doc"),
    )

    invoice = relationship(
        "Invoice",
        back_populates="supplier_copy",
        primaryjoin="and_(Invoice.company_id == SupplierInvoiceCopy.company_id, Invoice.id == SupplierInvoiceCopy.invoice_id)",
        overlaps="supplier_copies"
    )
    document = relationship(
        "Document",
        back_populates="supplier_copies",
        primaryjoin="and_(Document.company_id == SupplierInvoiceCopy.company_id, Document.id == SupplierInvoiceCopy.document_id)",
        overlaps="invoice,supplier_copy,supplier_copies"
    )
    superseding_user = relationship("User", foreign_keys=[superseded_by])


class OutboundSalesInvoice(Base):
    __tablename__ = "outbound_sales_invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, nullable=False, unique=True, index=True)
    company_id = Column(Integer, nullable=False, index=True)
    gst_registration_id = Column(Integer, nullable=False, index=True)
    customer_id = Column(Integer, nullable=False, index=True)
    billing_address_id = Column(Integer, nullable=True)
    shipping_address_id = Column(Integer, nullable=True)
    financial_year = Column(String(10), nullable=False)
    series_code = Column(String(20), nullable=False, default="INV")
    sequence_number = Column(Integer, nullable=True)
    place_of_supply_state_code = Column(String(2), nullable=False)
    place_of_supply_state_name = Column(String(100), nullable=False)
    place_of_supply = synonym("place_of_supply_state_code")
    reverse_charge = Column(Boolean, nullable=False, default=False)
    is_b2c = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    pdf_storage_key = Column(String(500), nullable=True)
    pdf_sha256 = Column(String(64), nullable=True)
    pdf_generated_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    is_discarded = Column(Boolean, nullable=False, default=False)
    discarded_at = Column(DateTime(timezone=True), nullable=True)
    discarded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    discard_reason = Column(Text, nullable=True)
    issuance_attempt_count = Column(Integer, nullable=False, default=0)
    issuance_started_at = Column(DateTime(timezone=True), nullable=True)
    issuance_error_details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "invoice_id", "gst_registration_id"],
            ["invoices.company_id", "invoices.id", "invoices.gst_registration_id"],
            name="fk_outbound_invoice_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id", "customer_id"],
            ["customers.company_id", "customers.id"],
            name="fk_outbound_customer_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "gst_registration_id"],
            ["gst_registrations.company_id", "gst_registrations.id"],
            name="fk_outbound_gst_reg_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_id", "billing_address_id"],
            ["customer_addresses.customer_id", "customer_addresses.id"],
            name="fk_outbound_billing_addr_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_id", "shipping_address_id"],
            ["customer_addresses.customer_id", "customer_addresses.id"],
            name="fk_outbound_shipping_addr_tenant",
            ondelete="RESTRICT",
        ),
    )

    invoice = relationship(
        "Invoice",
        back_populates="sales_detail",
        primaryjoin="and_(Invoice.company_id == OutboundSalesInvoice.company_id, Invoice.id == OutboundSalesInvoice.invoice_id)",
        overlaps="customer,gst_registration,sales_invoices"
    )
    customer = relationship(
        "Customer",
        back_populates="sales_invoices",
        primaryjoin="and_(Customer.company_id == OutboundSalesInvoice.company_id, Customer.id == OutboundSalesInvoice.customer_id)",
        overlaps="gst_registration,invoice,sales_detail,sales_invoices"
    )
    gst_registration = relationship(
        "GstRegistration",
        back_populates="sales_invoices",
        primaryjoin="and_(GstRegistration.company_id == OutboundSalesInvoice.company_id, GstRegistration.id == OutboundSalesInvoice.gst_registration_id)",
        overlaps="customer,invoice,sales_detail,sales_invoices"
    )
    billing_address = relationship(
        "CustomerAddress",
        foreign_keys=[billing_address_id],
        primaryjoin="and_(CustomerAddress.customer_id == OutboundSalesInvoice.customer_id, CustomerAddress.id == OutboundSalesInvoice.billing_address_id)"
    )
    shipping_address = relationship(
        "CustomerAddress",
        foreign_keys=[shipping_address_id],
        primaryjoin="and_(CustomerAddress.customer_id == OutboundSalesInvoice.customer_id, CustomerAddress.id == OutboundSalesInvoice.shipping_address_id)"
    )
    submitter = relationship("User", foreign_keys=[submitted_by])
    approver = relationship("User", foreign_keys=[approved_by])
    canceller = relationship("User", foreign_keys=[cancelled_by])


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    item_description = Column(Text, nullable=False)
    hsn_sac = Column(String(10), nullable=True)
    item_type = Column(String(10), nullable=False)  # 'goods', 'services'
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_of_measure = Column(String(20), nullable=False, default="nos")
    unit_price = Column(Numeric(14, 4), nullable=False)
    discount_percent = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    discount_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    taxable_value = Column(Numeric(15, 2), nullable=False)
    item_order = synonym("line_number")
    description = synonym("item_description")
    hsn_sac_code = synonym("hsn_sac")
    unit = synonym("unit_of_measure")
    taxable_amount = synonym("taxable_value")

    @property
    def gross_amount(self):
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    @property
    def total_tax_amount(self):
        return (self.cgst_amount or Decimal("0.00")) + (self.sgst_amount or Decimal("0.00")) + (self.igst_amount or Decimal("0.00"))

    @property
    def gst_classification(self):
        return "ZERO_RATED" if getattr(self, "is_zero_rated", False) else "TAXABLE"
    gst_rate = Column(Numeric(5, 2), nullable=False)
    cgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    cgst_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    sgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    sgst_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    igst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    igst_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    line_total = Column(Numeric(15, 2), nullable=False)
    is_zero_rated = Column(Boolean, nullable=False, default=False)
    zero_rate_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_item_line"),
    )

    invoice = relationship("Invoice", back_populates="items")


class SalesInvoiceSignature(Base):
    __tablename__ = "sales_invoice_signatures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, nullable=False)
    invoice_id = Column(Integer, nullable=False)
    storage_key = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    page_number = Column(Integer, default=1, nullable=False)
    is_pinned_to_last_page = Column(Boolean, default=False, nullable=False)
    x_mm = Column(Numeric(6, 2), nullable=False)
    y_mm = Column(Numeric(6, 2), nullable=False)
    width_mm = Column(Numeric(6, 2), nullable=False)
    height_mm = Column(Numeric(6, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "invoice_id"],
            ["invoices.company_id", "invoices.id"],
            name="fk_sales_invoice_signatures_invoice",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_sales_invoice_signatures_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint("page_number >= 1", name="chk_sig_page_number"),
        CheckConstraint("x_mm >= 0", name="chk_sig_x_mm"),
        CheckConstraint("y_mm >= 0", name="chk_sig_y_mm"),
        CheckConstraint("width_mm >= 10.0", name="chk_sig_width_mm"),
        CheckConstraint("height_mm >= 5.0", name="chk_sig_height_mm"),
        CheckConstraint("(x_mm + width_mm) <= 210.0", name="chk_sig_x_boundary"),
        CheckConstraint("(y_mm + height_mm) <= 297.0", name="chk_sig_y_boundary"),
    )

    invoice = relationship(
        "Invoice",
        back_populates="signatures",
        primaryjoin="and_(Invoice.company_id == SalesInvoiceSignature.company_id, Invoice.id == SalesInvoiceSignature.invoice_id)",
        overlaps="signatures",
    )
    company = relationship("Company", overlaps="invoice,signatures")


class TemporarySignatureUpload(Base):
    __tablename__ = "temporary_signature_uploads"

    upload_token_hash = Column(String(64), primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    storage_key = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    aspect_ratio = Column(Numeric(8, 4), nullable=False)
    width_px = Column(Integer, nullable=False)
    height_px = Column(Integer, nullable=False)
    consumed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    company = relationship("Company")
    branch = relationship("Branch")
    user = relationship("User")


# ── Module 9: Durable Processing Job Queue ───────────────────────────────────

class ProcessingJob(Base):
    """
    Module 9 — Durable PostgreSQL-backed document processing job queue.
    Eliminates fragile in-process BackgroundTasks by storing all pending,
    running, completed, and failed execution states persistently in the database.
    """
    __tablename__ = "processing_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE", name="fk_processing_jobs_document_id"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_processing_jobs_company_id"),
        nullable=False,
        index=True,
    )
    branch_id = Column(Integer, nullable=False, index=True)
    job_type = Column(String(50), nullable=False, default="ocr_extraction")
    status = Column(String(30), nullable=False, default="pending", index=True)  # pending, running, completed, failed
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    run_after = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    locked_by = Column(String(128), nullable=True, index=True)
    locked_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "uq_processing_jobs_active_doc",
            "document_id",
            "job_type",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        Index("ix_processing_jobs_claim", "status", "run_after"),
        Index("ix_processing_jobs_company_branch", "company_id", "branch_id"),
    )

    document = relationship("Document", back_populates="processing_jobs")
    company = relationship("Company")


# ── User Sessions (Durable Refresh-Token Sessions) ───────────────────────────

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    identity_type = Column(String(32), nullable=False)  # "master_admin" or "user"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    master_admin_id = Column(Integer, ForeignKey("master_admins.id", ondelete="CASCADE"), nullable=True, index=True)
    token_hash = Column(String(128), unique=True, nullable=False, index=True)
    family_id = Column(String(64), nullable=False, index=True)
    parent_session_id = Column(Integer, nullable=True)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(64), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(identity_type = 'user' AND user_id IS NOT NULL AND master_admin_id IS NULL) OR "
            "(identity_type = 'master_admin' AND master_admin_id IS NOT NULL AND user_id IS NULL)",
            name="chk_user_session_identity",
        ),
        Index("ix_user_sessions_family", "family_id"),
    )

    user = relationship("User", back_populates="sessions")
    master_admin = relationship("MasterAdmin", back_populates="sessions")


# ── Invitations ──────────────────────────────────────────────────────────────

class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_invitations_company_id"),
        nullable=False,
        index=True,
    )
    branch_id = Column(Integer, nullable=False, index=True)
    invited_role = Column(Enum(UserRole, name="userrole"), nullable=False)
    token_hash = Column(String(128), unique=True, nullable=False, index=True)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_invitations_company_branch",
            ondelete="CASCADE",
        ),
        Index("ix_invitations_company_branch", "company_id", "branch_id"),
    )

    company = relationship("Company")
    branch = relationship("Branch", foreign_keys=[branch_id])
    inviter = relationship("User", foreign_keys=[invited_by])


# ── Password Resets ──────────────────────────────────────────────────────────

class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True)
    identity_type = Column(String(32), nullable=False)  # "master_admin" or "user"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    master_admin_id = Column(Integer, ForeignKey("master_admins.id", ondelete="CASCADE"), nullable=True, index=True)
    token_hash = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    requested_ip = Column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(identity_type = 'user' AND user_id IS NOT NULL AND master_admin_id IS NULL) OR "
            "(identity_type = 'master_admin' AND master_admin_id IS NOT NULL AND user_id IS NULL)",
            name="chk_password_reset_identity",
        ),
    )

    user = relationship("User")
    master_admin = relationship("MasterAdmin")


# ── Company Onboarding (Application & Multi-Stage Review) ─────────────────────

class CompanyOnboarding(Base):
    __tablename__ = "company_onboardings"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(
        Enum(OnboardingStatus, name="onboardingstatus", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=OnboardingStatus.PENDING_SUBMISSION,
        index=True,
    )

    # Initial admin inputs
    initial_company_name = Column(String(255), nullable=False)
    contact_name = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=False, index=True)
    created_by_admin_id = Column(Integer, ForeignKey("master_admins.id", ondelete="SET NULL"), nullable=True)

    # Section A – Company details
    legal_company_name = Column(String(255), nullable=True)
    trade_name = Column(String(255), nullable=True)
    business_type = Column(String(100), nullable=True)
    business_description = Column(Text, nullable=True)
    year_of_establishment = Column(String(32), nullable=True)
    company_website = Column(String(255), nullable=True)

    # Section B – Indian business and tax details
    pan_number = Column(String(32), nullable=True)
    gstin = Column(String(32), nullable=True)
    gst_type = Column(String(64), nullable=True)
    cin = Column(String(32), nullable=True)
    llpin = Column(String(32), nullable=True)
    udyam_number = Column(String(64), nullable=True)
    tan = Column(String(32), nullable=True)

    # Section C – Registered office and business address
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True, default="India")

    # Section D – Authorized contact person
    auth_contact_name = Column(String(255), nullable=True)
    auth_contact_designation = Column(String(100), nullable=True)
    auth_contact_email = Column(String(255), nullable=True)
    auth_contact_mobile = Column(String(32), nullable=True)
    auth_contact_alternate_mobile = Column(String(32), nullable=True)

    # Section E – Company branches
    has_multiple_branches = Column(Boolean, nullable=True, default=False)
    branch_details = Column(JSON, nullable=True, default=list)

    # Section F – First company administrator
    admin_name = Column(String(255), nullable=True)
    admin_email = Column(String(255), nullable=True)
    admin_password_hash = Column(String(255), nullable=True)
    admin_mobile = Column(String(32), nullable=True)
    admin_designation = Column(String(100), nullable=True)

    # Section G – Document and business preferences
    primary_document_types = Column(JSON, nullable=True, default=list)
    expected_monthly_volume = Column(String(64), nullable=True)
    languages = Column(JSON, nullable=True, default=list)
    timezone = Column(String(64), nullable=True, default="Asia/Kolkata")
    currency = Column(String(32), nullable=True, default="INR")

    # Document uploads metadata
    uploaded_documents = Column(JSON, nullable=True, default=dict)

    # Master Admin Review Lifecycle
    review_comments = Column(Text, nullable=True)
    review_history = Column(JSON, nullable=True, default=list)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_by_admin = relationship("MasterAdmin")
    approved_company = relationship("Company")


class AuditLog(Base):
    """
    Module 5 – Tamper-resistant, immutable audit logs.
    Captures security-relevant actions across companies, branches, and platform administration.
    """
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    actor_type = Column(String(50), nullable=False, index=True)
    actor_id = Column(Integer, nullable=True)
    company_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    object_type = Column(String(50), nullable=True, index=True)
    object_id = Column(String(100), nullable=True, index=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_audit_logs_company_occurred_at", "company_id", "occurred_at"),
        Index("ix_audit_logs_actor", "actor_type", "actor_id"),
        Index("ix_audit_logs_object", "object_type", "object_id"),
    )


# ── Module 6 – Multi-Factor Authentication (TOTP & Recovery) ─────────────────

class UserMfa(Base):
    __tablename__ = "user_mfa"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_mfa_user_id"),
        nullable=True,
        unique=True,
        index=True,
    )
    master_admin_id = Column(
        Integer,
        ForeignKey("master_admins.id", ondelete="CASCADE", name="fk_user_mfa_master_admin_id"),
        nullable=True,
        unique=True,
        index=True,
    )
    encrypted_secret = Column(Text, nullable=False)
    enabled_at = Column(DateTime, nullable=True)  # NULL until TOTP is verified during enrollment
    last_used_step = Column(BigInteger, nullable=True)  # Replay attack prevention: stores TOTP time step
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND master_admin_id IS NULL) OR (user_id IS NULL AND master_admin_id IS NOT NULL)",
            name="chk_user_mfa_exclusive_identity",
        ),
    )

    user = relationship("User", backref="mfa_config")
    master_admin = relationship("MasterAdmin", backref="mfa_config")
    recovery_codes = relationship("MfaRecoveryCode", back_populates="user_mfa", cascade="all, delete-orphan")


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_mfa_id = Column(
        Integer,
        ForeignKey("user_mfa.id", ondelete="CASCADE", name="fk_mfa_recovery_codes_user_mfa_id"),
        nullable=False,
        index=True,
    )
    code_hash = Column(String(128), nullable=False, index=True)  # SHA-256 hash of single-use recovery code
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_mfa = relationship("UserMfa", back_populates="recovery_codes")


class PlatformSetting(Base):
    """
    Platform-wide settings managed by Master Admins (e.g. global MFA enforcement policies).
    """
    __tablename__ = "platform_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(
        Integer,
        ForeignKey("master_admins.id", ondelete="SET NULL", name="fk_platform_settings_master_admin_id"),
        nullable=True,
    )

    master_admin = relationship("MasterAdmin")


class AIUsageLedger(Base):
    """
    Module 7 – AI Usage & Monthly Budget Ledger.
    Tracks token counts, cost cents, and operations across tenant companies.
    """
    __tablename__ = "ai_usage_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), nullable=False)  # gemini, gpt, claude
    model = Column(String(100), nullable=False)
    operation = Column(String(50), nullable=False)  # ocr, extraction, classification, chat
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)
    cost_cents = Column(Integer, nullable=False, default=0)
    cost_inr = Column(Numeric(12, 4), nullable=False, default=0.0)
    exchange_rate = Column(Numeric(10, 4), nullable=False, default=85.0)
    converted_at = Column(DateTime, default=datetime.utcnow)
    currency = Column(String(10), nullable=False, default="INR")
    status = Column(String(32), nullable=False, default="success")  # success, failed
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    company = relationship("Company")
    branch = relationship("Branch")


# ── Module 10: Multi-Provider AI Architecture ───────────────────────────────

class PlatformAIProvider(Base):
    """Platform-level AI provider catalogue and approved model allow-lists (Master Admin controlled)."""
    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, index=True)
    provider_key = Column(String(32), unique=True, nullable=False, index=True)  # 'gemini', 'openai', 'anthropic'
    display_name = Column(String(64), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    model_allow_list = Column(JSON, nullable=False, default=list)
    supported_operations = Column(JSON, nullable=False, default=lambda: ["read", "generate"])
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompanyAISetting(Base):
    """Company-scoped permitted providers, defaults, and constraints."""
    __tablename__ = "company_ai_settings"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_company_ai_settings_company_id"),
        unique=True,
        nullable=False,
        index=True,
    )
    allowed_providers = Column(JSON, nullable=False, default=lambda: ["gemini", "openai", "anthropic"])
    default_read_provider = Column(String(32), nullable=True)
    default_read_model = Column(String(64), nullable=True)
    default_generate_provider = Column(String(32), nullable=True)
    default_generate_model = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", backref="ai_setting", uselist=False)


class CompanyAIConsent(Base):
    """Company-level consent recorded explicitly per external AI provider."""
    __tablename__ = "company_ai_consents"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_company_ai_consents_company_id"),
        nullable=False,
        index=True,
    )
    provider_key = Column(String(32), nullable=False, index=True)
    is_consented = Column(Boolean, nullable=False, default=False)
    consented_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    consented_at = Column(DateTime, nullable=True)
    policy_version = Column(String(32), nullable=False, default="1.0")
    revoked_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("uq_company_ai_consents_provider", "company_id", "provider_key", unique=True),
    )

    company = relationship("Company")
    consenter = relationship("User", foreign_keys=[consented_by])
    revoker = relationship("User", foreign_keys=[revoked_by])


class BranchAIConfig(Base):
    """Branch-level operation mapping for read/generate operations with primary/fallback providers and models."""
    __tablename__ = "branch_ai_configs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_branch_ai_configs_company_id"),
        nullable=False,
        index=True,
    )
    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="CASCADE", name="fk_branch_ai_configs_branch_id"),
        nullable=False,
        index=True,
    )
    operation = Column(String(32), nullable=False)  # 'read' or 'generate'
    primary_provider = Column(String(32), nullable=False)
    primary_model = Column(String(64), nullable=False)
    fallback_provider = Column(String(32), nullable=True)
    fallback_model = Column(String(64), nullable=True)
    max_retries = Column(Integer, nullable=False, default=2)
    timeout_seconds = Column(Integer, nullable=False, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("uq_branch_ai_configs_op", "company_id", "branch_id", "operation", unique=True),
    )

    company = relationship("Company")
    branch = relationship("Branch")


class AICredential(Base):
    """Encrypted AI credentials stored at platform, company, or branch scope with write-only masking."""
    __tablename__ = "ai_credentials"

    id = Column(Integer, primary_key=True, index=True)
    provider_key = Column(String(32), nullable=False, index=True)
    scope_type = Column(String(32), nullable=False)  # 'platform', 'company', 'branch'
    scope_id = Column(Integer, nullable=True)        # null for platform, company_id or branch_id
    encrypted_key = Column(Text, nullable=False)
    key_version = Column(Integer, nullable=False, default=1)
    masked_key = Column(String(32), nullable=False)   # e.g. '************ABCD'
    status = Column(String(32), nullable=False, default="active")  # 'active', 'disabled'
    last_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index(
            "uq_ai_credentials_scope",
            "provider_key",
            "scope_type",
            text("COALESCE(scope_id, 0)"),
            unique=True,
        ),
    )


class AIProcessingLog(Base):
    """Detailed attempt-level AI execution log with latency, token consumption, and cost tracking."""
    __tablename__ = "ai_processing_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_ai_processing_logs_company_id"),
        nullable=False,
        index=True,
    )
    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="SET NULL", name="fk_ai_processing_logs_branch_id"),
        nullable=True,
        index=True,
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL", name="fk_ai_processing_logs_document_id"),
        nullable=True,
        index=True,
    )
    job_id = Column(
        BigInteger,
        ForeignKey("processing_jobs.id", ondelete="SET NULL", name="fk_ai_processing_logs_job_id"),
        nullable=True,
        index=True,
    )
    operation = Column(String(32), nullable=False)  # 'read', 'generate'
    provider = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    is_fallback = Column(Boolean, nullable=False, default=False)
    attempt_number = Column(Integer, nullable=False, default=1)
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)
    cost_cents = Column(Integer, nullable=False, default=0)
    cost_inr = Column(Numeric(12, 4), nullable=False, default=0.0)
    exchange_rate = Column(Numeric(10, 4), nullable=False, default=85.0)
    converted_at = Column(DateTime, default=datetime.utcnow)
    currency = Column(String(10), nullable=False, default="INR")
    latency_ms = Column(Integer, nullable=False, default=0)
    success = Column(Boolean, nullable=False, default=True)
    error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_ai_processing_logs_comp_created", "company_id", "created_at"),
    )

    company = relationship("Company")
    branch = relationship("Branch")
    document = relationship("Document")
    job = relationship("ProcessingJob")


# ── Module 11 – Document Templates and Human Review ──────────────────────────

class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_document_templates_company_id"),
        nullable=True,
        index=True,
    )
    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="SET NULL", name="fk_document_templates_branch_id"),
        nullable=True,
        index=True,
    )
    document_type = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(32), nullable=False, default="extraction")
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active")  # 'active', 'inactive'
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_document_templates_created_by"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_doc_templates_lookup", "company_id", "branch_id", "document_type", "status"),
    )

    company = relationship("Company")
    branch = relationship("Branch")
    creator = relationship("User", foreign_keys=[created_by])
    versions = relationship(
        "TemplateVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateVersion.version_number",
    )


class TemplateVersion(Base):
    __tablename__ = "template_versions"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(
        Integer,
        ForeignKey("document_templates.id", ondelete="CASCADE", name="fk_template_versions_template_id"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    schema_json = Column(JSONB, nullable=False)
    validation_rules = Column(JSONB, nullable=False, default=list)
    extraction_instructions = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft")  # 'draft', 'published', 'retired'
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_template_versions_created_by"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("template_id", "version_number", name="uq_template_version_number"),
        Index("ix_template_versions_lookup", "template_id", "status"),
    )

    template = relationship("DocumentTemplate", back_populates="versions")
    creator = relationship("User", foreign_keys=[created_by])


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE", name="fk_document_extractions_document_id"),
        nullable=False,
        unique=True,
        index=True,
    )
    template_version_id = Column(
        Integer,
        ForeignKey("template_versions.id", ondelete="RESTRICT", name="fk_document_extractions_template_version_id"),
        nullable=False,
        index=True,
    )
    data = Column(JSONB, nullable=False, default=dict)
    raw_text = Column(Text, nullable=True)  # Original OCR text, strictly immutable upon human corrections
    validation_flags = Column(JSONB, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="extracted")  # 'pending', 'extracted', 'needs_review', 'approved', 'rejected'
    reviewed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_document_extractions_reviewed_by"),
        nullable=True,
    )
    reviewed_at = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)  # Optimistic concurrency lock
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="extraction")
    template_version = relationship("TemplateVersion")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    edits = relationship(
        "ExtractionEdit",
        back_populates="extraction",
        cascade="all, delete-orphan",
        order_by="ExtractionEdit.id.desc()",
    )


class ExtractionEdit(Base):
    __tablename__ = "extraction_edits"

    id = Column(Integer, primary_key=True, index=True)
    document_extraction_id = Column(
        Integer,
        ForeignKey("document_extractions.id", ondelete="CASCADE", name="fk_extraction_edits_document_extraction_id"),
        nullable=False,
        index=True,
    )
    field_path = Column(String(255), nullable=False)
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    edited_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_extraction_edits_edited_by"),
        nullable=True,
    )
    edited_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    extraction = relationship("DocumentExtraction", back_populates="edits")
    editor = relationship("User", foreign_keys=[edited_by])





