"""module13_invoice_generation

Revision ID: p1q2r3s4t5u6
Revises: o1p2q3r4s5t6
Create Date: 2026-11-12 14:00:00.000000

Module 13 – Invoice Generation (Re-scoped):
- Separate Standardised Supplier Copies and Outbound Sales Invoices.
- Composite tenant-safe foreign keys for all tenant-scoped relationships.
- Decimal/NUMERIC precision for all financial columns.
- Master tables: gst_registrations, customers, customer_addresses, expense_categories, hsn_sac_rates, number_sequences.
- Expand invoices table with kind, status, and financial fields.
- Detail tables: supplier_invoice_copies and outbound_sales_invoices.
- Normalized invoice_items table for outbound sales invoices.
- Non-destructive backfill of legacy invoice row 106 (Document 492).
- Restrictive foreign key cascades on accounting and invoice records.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'p1q2r3s4t5u6'
down_revision: Union[str, Sequence[str], None] = 'o1p2q3r4s5t6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # ── 1. Company Approval Policy & Tenant Unique Keys ─────────────────────────
    op.add_column(
        'companies',
        sa.Column('invoice_approval_policy', sa.String(50), nullable=False, server_default='admin_only')
    )
    op.create_check_constraint(
        'chk_company_approval_policy',
        'companies',
        "invoice_approval_policy IN ('admin_only', 'allow_self_approval')"
    )

    # Ensure documents has unique (company_id, id) for tenant composite FKs
    op.create_unique_constraint('uq_documents_company_id', 'documents', ['company_id', 'id'])

    # Ensure invoices has unique (company_id, id) for tenant composite FKs
    op.create_unique_constraint('uq_invoices_company_id', 'invoices', ['company_id', 'id'])

    # ── 2. Master Tables: GST Registrations ──────────────────────────────────────
    op.create_table(
        'gst_registrations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('gstin', sa.String(15), nullable=False, unique=True),
        sa.Column('legal_name', sa.String(255), nullable=False),
        sa.Column('trade_name', sa.String(255), nullable=True),
        sa.Column('state_code', sa.String(2), nullable=False),
        sa.Column('state_name', sa.String(100), nullable=False),
        sa.Column('registered_address', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('company_id', 'id', name='uq_gst_reg_company_tenant'),
        sa.CheckConstraint(
            "gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'",
            name='chk_gst_reg_format'
        )
    )
    op.create_index(
        'uq_company_default_gst_reg',
        'gst_registrations',
        ['company_id'],
        unique=True,
        postgresql_where=sa.text('is_default = TRUE AND is_active = TRUE')
    )

    # Allow branches to link to company GST registration
    op.add_column(
        'branches',
        sa.Column('gst_registration_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_branches_gst_reg_tenant',
        'branches',
        'gst_registrations',
        ['company_id', 'gst_registration_id'],
        ['company_id', 'id'],
        ondelete='SET NULL'
    )

    # ── 3. Master Tables: Customers & Customer Addresses ────────────────────────
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('customer_code', sa.String(50), nullable=True),
        sa.Column('legal_name', sa.String(255), nullable=False),
        sa.Column('trade_name', sa.String(255), nullable=True),
        sa.Column('gstin', sa.String(15), nullable=True),
        sa.Column('pan', sa.String(10), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('is_b2c', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('company_id', 'id', name='uq_customers_company_tenant'),
        sa.CheckConstraint(
            "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'",
            name='chk_customer_gstin_format'
        )
    )

    op.create_table(
        'customer_addresses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('address_type', sa.String(20), nullable=False),
        sa.Column('address_line1', sa.String(255), nullable=False),
        sa.Column('address_line2', sa.String(255), nullable=True),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('state_code', sa.String(2), nullable=False),
        sa.Column('state_name', sa.String(100), nullable=False),
        sa.Column('pincode', sa.String(20), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('customer_id', 'id', name='uq_customer_address_tenant'),
        sa.CheckConstraint("address_type IN ('billing', 'shipping', 'both')", name='chk_customer_address_type')
    )

    # ── 4. Master Tables: Expense Categories ────────────────────────────────────
    op.create_table(
        'expense_categories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('company_id', 'id', name='uq_expense_cat_company_tenant'),
        sa.UniqueConstraint('company_id', 'code', name='uq_expense_cat_company_code')
    )

    # Seed default General category for all existing companies
    op.execute("""
        INSERT INTO expense_categories (company_id, code, name, description, is_active)
        SELECT id, 'GEN', 'General / Uncategorised', 'Default expense category', TRUE
        FROM companies
        ON CONFLICT DO NOTHING;
    """)

    # Attach category_id to documents
    op.add_column(
        'documents',
        sa.Column('category_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_documents_category_tenant',
        'documents',
        'expense_categories',
        ['company_id', 'category_id'],
        ['company_id', 'id'],
        ondelete='SET NULL'
    )

    # ── 5. Reference Data: HSN/SAC Catalogue ────────────────────────────────────
    op.create_table(
        'hsn_sac_rates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('item_type', sa.String(10), nullable=False),
        sa.Column('gst_rate', sa.Numeric(5, 2), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('code', 'item_type', 'effective_from', name='uq_hsn_sac_timeline'),
        sa.CheckConstraint("item_type IN ('goods', 'services')", name='chk_hsn_sac_item_type')
    )

    # ── 6. Master Tables: Number Sequences ──────────────────────────────────────
    op.create_table(
        'number_sequences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('gst_registration_id', sa.Integer(), nullable=False),
        sa.Column('financial_year', sa.String(10), nullable=False),
        sa.Column('series_code', sa.String(20), nullable=False, server_default='INV'),
        sa.Column('next_value', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('padding', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(
            ['company_id', 'gst_registration_id'],
            ['gst_registrations.company_id', 'gst_registrations.id'],
            name='fk_sequence_gst_tenant',
            ondelete='RESTRICT'
        ),
        sa.UniqueConstraint(
            'company_id', 'gst_registration_id', 'financial_year', 'series_code',
            name='uq_number_sequence_tenant'
        )
    )

    # ── 7. Expand Invoices Header Table ─────────────────────────────────────────
    # Relax existing restrictive constraints
    op.drop_constraint('invoices_document_id_fkey', 'invoices', type_='foreignkey')
    op.create_foreign_key(
        'invoices_document_id_fkey',
        'invoices',
        'documents',
        ['document_id'],
        ['id'],
        ondelete='RESTRICT'
    )
    op.drop_constraint('fk_invoices_company_id', 'invoices', type_='foreignkey')
    op.create_foreign_key(
        'fk_invoices_company_id',
        'invoices',
        'companies',
        ['company_id'],
        ['id'],
        ondelete='RESTRICT'
    )
    op.drop_constraint('fk_invoices_company_branch', 'invoices', type_='foreignkey')
    op.create_foreign_key(
        'fk_invoices_company_branch',
        'invoices',
        'branches',
        ['company_id', 'branch_id'],
        ['company_id', 'id'],
        ondelete='RESTRICT'
    )

    op.alter_column('invoices', 'document_id', nullable=True)
    op.alter_column('invoices', 'uploaded_by', nullable=True)
    op.alter_column('invoices', 'pdf_filename', nullable=True)

    # Drop old global unique index on document_id so multiple outbound invoices can have document_id = NULL
    op.drop_index('ix_invoices_document_id', table_name='invoices')
    op.create_index('ix_invoices_document_id', 'invoices', ['document_id'], unique=False)

    # Add new architectural header columns
    op.add_column('invoices', sa.Column('kind', sa.String(20), nullable=False, server_default='copy'))
    op.add_column('invoices', sa.Column('status', sa.String(30), nullable=False, server_default='available'))
    op.add_column('invoices', sa.Column('due_date', sa.Date(), nullable=True))
    op.add_column('invoices', sa.Column('taxable_amount', sa.Numeric(15, 2), nullable=True))
    op.add_column('invoices', sa.Column('cgst_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'))
    op.add_column('invoices', sa.Column('sgst_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'))
    op.add_column('invoices', sa.Column('igst_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'))
    op.add_column('invoices', sa.Column('round_off', sa.Numeric(15, 2), nullable=False, server_default='0.00'))
    op.add_column('invoices', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('invoices', sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))
    op.add_column('invoices', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')))

    # Immediately backfill existing row 106 so check constraints succeed
    op.execute("""
        UPDATE invoices
        SET kind = 'copy',
            status = 'available',
            invoice_date = '2026-03-19',
            grand_total = '96000.00',
            taxable_amount = 81355.95,
            cgst_amount = 7322.04,
            sgst_amount = 7322.04,
            igst_amount = 0.00,
            round_off = -0.03,
            currency = 'INR'
        WHERE id = 106;
    """)
    op.execute("ALTER TABLE invoices ALTER COLUMN invoice_date TYPE date USING invoice_date::date;")
    op.execute("ALTER TABLE invoices ALTER COLUMN grand_total TYPE numeric(15, 2) USING grand_total::numeric(15, 2);")

    # Add CHECK constraints on invoices
    op.create_check_constraint(
        'chk_invoices_kind_status',
        'invoices',
        """(kind = 'copy' AND status IN ('available', 'stale', 'superseded')) OR
           (kind = 'generated' AND status IN ('draft', 'pending_approval', 'pending_issuance', 'approved', 'cancelled'))"""
    )
    op.create_check_constraint(
        'chk_invoices_financial_completeness',
        'invoices',
        """(kind = 'copy') OR
           (kind = 'generated' AND status = 'draft') OR
           (kind = 'generated' AND status IN ('pending_approval', 'pending_issuance', 'approved', 'cancelled') AND
            taxable_amount IS NOT NULL AND taxable_amount >= 0 AND
            grand_total IS NOT NULL AND grand_total >= 0 AND
            currency IS NOT NULL)"""
    )
    op.create_check_constraint(
        'chk_invoices_number_requirement',
        'invoices',
        """(kind = 'copy') OR
           (kind = 'generated' AND status IN ('draft', 'pending_approval') AND invoice_number IS NULL) OR
           (kind = 'generated' AND status IN ('pending_issuance', 'approved', 'cancelled') AND invoice_number IS NOT NULL)"""
    )

    # Scoped unique index for outbound sales invoice numbers
    op.create_index(
        'uq_company_sales_invoice_number',
        'invoices',
        ['company_id', 'invoice_number'],
        unique=True,
        postgresql_where=sa.text("kind = 'generated' AND invoice_number IS NOT NULL")
    )

    # ── 8. Detail Table: Supplier Invoice Copies ────────────────────────────────
    op.create_table(
        'supplier_invoice_copies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), nullable=False, index=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('supplier_invoice_number', sa.String(100), nullable=True),
        sa.Column('supplier_name', sa.String(255), nullable=True),
        sa.Column('supplier_gstin', sa.String(15), nullable=True),
        sa.Column('copy_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_stale', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('source_data_hash', sa.String(64), nullable=False),
        sa.Column('template_version_id', sa.Integer(), nullable=True),
        sa.Column('pdf_storage_key', sa.String(500), nullable=False),
        sa.Column('pdf_sha256', sa.String(64), nullable=False),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('superseded_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(
            ['company_id', 'invoice_id'],
            ['invoices.company_id', 'invoices.id'],
            name='fk_copy_invoice_tenant',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['company_id', 'document_id'],
            ['documents.company_id', 'documents.id'],
            name='fk_copy_document_tenant',
            ondelete='RESTRICT'
        ),
        sa.UniqueConstraint('document_id', 'copy_version', name='uq_copy_version_per_doc')
    )
    op.create_index(
        'uq_current_copy_per_document',
        'supplier_invoice_copies',
        ['document_id'],
        unique=True,
        postgresql_where=sa.text('is_current = TRUE')
    )

    # ── 9. Detail Table: Outbound Sales Invoices ─────────────────────────────────
    op.create_table(
        'outbound_sales_invoices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('gst_registration_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('billing_address_id', sa.Integer(), nullable=True),
        sa.Column('shipping_address_id', sa.Integer(), nullable=True),
        sa.Column('financial_year', sa.String(10), nullable=False),
        sa.Column('series_code', sa.String(20), nullable=False, server_default='INV'),
        sa.Column('sequence_number', sa.Integer(), nullable=True),
        sa.Column('place_of_supply_state_code', sa.String(2), nullable=False),
        sa.Column('place_of_supply_state_name', sa.String(100), nullable=False),
        sa.Column('reverse_charge', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_b2c', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('pdf_storage_key', sa.String(500), nullable=True),
        sa.Column('pdf_sha256', sa.String(64), nullable=True),
        sa.Column('pdf_generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submitted_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column('is_discarded', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('discarded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('discarded_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('discard_reason', sa.Text(), nullable=True),
        sa.Column('issuance_attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('issuance_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('issuance_error_details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(
            ['company_id', 'invoice_id'],
            ['invoices.company_id', 'invoices.id'],
            name='fk_outbound_invoice_tenant',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['company_id', 'customer_id'],
            ['customers.company_id', 'customers.id'],
            name='fk_outbound_customer_tenant',
            ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['company_id', 'gst_registration_id'],
            ['gst_registrations.company_id', 'gst_registrations.id'],
            name='fk_outbound_gst_reg_tenant',
            ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['customer_id', 'billing_address_id'],
            ['customer_addresses.customer_id', 'customer_addresses.id'],
            name='fk_outbound_billing_addr_tenant',
            ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['customer_id', 'shipping_address_id'],
            ['customer_addresses.customer_id', 'customer_addresses.id'],
            name='fk_outbound_shipping_addr_tenant',
            ondelete='RESTRICT'
        )
    )
    op.create_index(
        'uq_outbound_invoice_sequence',
        'outbound_sales_invoices',
        ['company_id', 'gst_registration_id', 'financial_year', 'series_code', 'sequence_number'],
        unique=True,
        postgresql_where=sa.text('sequence_number IS NOT NULL')
    )

    # ── 10. Normalized Line Items Table ─────────────────────────────────────────
    op.create_table(
        'invoice_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('item_description', sa.Text(), nullable=False),
        sa.Column('hsn_sac', sa.String(10), nullable=True),
        sa.Column('item_type', sa.String(10), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_of_measure', sa.String(20), nullable=False, server_default='nos'),
        sa.Column('unit_price', sa.Numeric(14, 4), nullable=False),
        sa.Column('discount_percent', sa.Numeric(5, 2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('taxable_value', sa.Numeric(15, 2), nullable=False),
        sa.Column('gst_rate', sa.Numeric(5, 2), nullable=False),
        sa.Column('cgst_rate', sa.Numeric(5, 2), nullable=False, server_default='0.00'),
        sa.Column('cgst_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('sgst_rate', sa.Numeric(5, 2), nullable=False, server_default='0.00'),
        sa.Column('sgst_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('igst_rate', sa.Numeric(5, 2), nullable=False, server_default='0.00'),
        sa.Column('igst_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('line_total', sa.Numeric(15, 2), nullable=False),
        sa.Column('is_zero_rated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('zero_rate_reason', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('invoice_id', 'line_number', name='uq_invoice_item_line'),
        sa.CheckConstraint("item_type IN ('goods', 'services')", name='chk_invoice_item_type'),
        sa.CheckConstraint("quantity > 0", name='chk_invoice_item_quantity'),
        sa.CheckConstraint("unit_price >= 0", name='chk_invoice_item_unit_price'),
        sa.CheckConstraint("discount_percent >= 0 AND discount_percent <= 100", name='chk_invoice_item_disc_pct'),
        sa.CheckConstraint("discount_amount >= 0", name='chk_invoice_item_disc_amt'),
        sa.CheckConstraint("taxable_value >= 0", name='chk_invoice_item_taxable'),
        sa.CheckConstraint("line_total >= 0", name='chk_invoice_item_line_total')
    )

    # Trigger to ensure line items can ONLY be attached to outbound sales invoices (kind = 'generated')
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_fn_check_invoice_item_kind()
        RETURNS TRIGGER AS $$
        DECLARE
            v_kind VARCHAR(20);
        BEGIN
            SELECT kind INTO v_kind FROM invoices WHERE id = NEW.invoice_id;
            IF v_kind != 'generated' THEN
                RAISE EXCEPTION 'Cannot attach invoice line items to invoice kind: %. Items are permitted only for kind generated.', v_kind;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_invoice_item_kind_check
        BEFORE INSERT OR UPDATE ON invoice_items
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_check_invoice_item_kind();

        -- Immutability enforcement: prevent physical deletion of issued or in-process invoices
        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_invoice_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.kind = 'generated' AND OLD.status IN ('pending_issuance', 'approved', 'cancelled') THEN
                RAISE EXCEPTION 'Cannot physically delete issued or in-process invoice %. Issued invoices are immutable.', OLD.id;
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_invoices_prevent_delete ON invoices;
        CREATE TRIGGER trg_invoices_prevent_delete
        BEFORE DELETE ON invoices
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_prevent_issued_invoice_delete();

        -- Immutability enforcement: prevent modification or deletion of line items on issued invoices
        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_invoice_item_mutation()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(50);
            v_inv_id INT;
        BEGIN
            v_inv_id := COALESCE(NEW.invoice_id, OLD.invoice_id);
            SELECT status INTO v_status FROM invoices WHERE id = v_inv_id;
            IF v_status IN ('pending_issuance', 'approved', 'cancelled') THEN
                RAISE EXCEPTION 'Cannot modify or delete invoice line items for issued invoice % in status %. Line items are immutable.', v_inv_id, v_status;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            ELSE
                RETURN NEW;
            END IF;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_invoice_items_prevent_mutation ON invoice_items;
        CREATE TRIGGER trg_invoice_items_prevent_mutation
        BEFORE INSERT OR UPDATE OR DELETE ON invoice_items
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_prevent_issued_invoice_item_mutation();
    """)

    # ── 11. Backfill Legacy Record 106 Detail into supplier_invoice_copies ─────
    op.execute("""
        INSERT INTO supplier_invoice_copies (
            invoice_id,
            company_id,
            document_id,
            supplier_invoice_number,
            supplier_name,
            supplier_gstin,
            copy_version,
            is_current,
            is_stale,
            source_data_hash,
            pdf_storage_key,
            pdf_sha256,
            created_at
        )
        SELECT
            106,
            24,
            492,
            'LC-25-26/4280',
            'LUCKY COMPUTERS',
            '33BLAPS0819R1ZQ',
            1,
            TRUE,
            FALSE,
            '0d9e70b192126dc8287e3cf992edc4d925a7f441521bd5e5c5499bd5a18c29d0',
            'generated_invoice_492.pdf',
            '733c6cc69db11d086f76415a2459dfa42c8b5fddc0665f10671e3d9f720e635a',
            NOW()
        WHERE EXISTS (
            SELECT 1 FROM invoices i
            JOIN documents d ON d.id = 492 AND d.company_id = 24
            WHERE i.id = 106 AND i.company_id = 24
        )
        ON CONFLICT (document_id, copy_version) DO NOTHING;
    """)


def downgrade():
    bind = op.get_bind()
    # Refuse downgrade if new sales invoices exist
    has_new_sales = bind.execute(
        sa.text("SELECT COUNT(*) FROM invoices WHERE kind = 'generated' AND id != 106")
    ).scalar()
    if has_new_sales and has_new_sales > 0:
        raise RuntimeError(
            f"Downgrade rejected: Database contains {has_new_sales} outbound sales "
            "invoice records that cannot be represented in the legacy schema. "
            "Refusing to delete issued accounting records."
        )

    op.execute("DROP TRIGGER IF EXISTS trg_invoices_prevent_delete ON invoices;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_prevent_issued_invoice_delete();")
    op.execute("DROP TRIGGER IF EXISTS trg_invoice_items_prevent_mutation ON invoice_items;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_prevent_issued_invoice_item_mutation();")
    op.execute("DROP TRIGGER IF EXISTS trg_invoice_item_kind_check ON invoice_items;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_check_invoice_item_kind();")

    op.drop_table('invoice_items')
    op.drop_table('outbound_sales_invoices')
    op.drop_table('supplier_invoice_copies')

    op.drop_constraint('chk_invoices_number_requirement', 'invoices', type_='check')
    op.drop_constraint('chk_invoices_financial_completeness', 'invoices', type_='check')
    op.drop_constraint('chk_invoices_kind_status', 'invoices', type_='check')
    op.drop_index('uq_company_sales_invoice_number', table_name='invoices')

    op.drop_column('invoices', 'updated_at')
    op.drop_column('invoices', 'created_by')
    op.drop_column('invoices', 'notes')
    op.drop_column('invoices', 'round_off')
    op.drop_column('invoices', 'igst_amount')
    op.drop_column('invoices', 'sgst_amount')
    op.drop_column('invoices', 'cgst_amount')
    op.drop_column('invoices', 'taxable_amount')
    op.drop_column('invoices', 'due_date')
    op.drop_column('invoices', 'status')
    op.drop_column('invoices', 'kind')

    op.drop_table('number_sequences')
    op.drop_table('hsn_sac_rates')

    op.drop_constraint('fk_documents_category_tenant', 'documents', type_='foreignkey')
    op.drop_column('documents', 'category_id')
    op.drop_table('expense_categories')

    op.drop_table('customer_addresses')
    op.drop_table('customers')

    op.drop_constraint('fk_branches_gst_reg_tenant', 'branches', type_='foreignkey')
    op.drop_column('branches', 'gst_registration_id')
    op.drop_table('gst_registrations')

    op.drop_constraint('chk_company_approval_policy', 'companies', type_='check')
    op.drop_column('companies', 'invoice_approval_policy')

    op.drop_constraint('uq_invoices_company_id', 'invoices', type_='unique')
    op.drop_constraint('uq_documents_company_id', 'documents', type_='unique')
