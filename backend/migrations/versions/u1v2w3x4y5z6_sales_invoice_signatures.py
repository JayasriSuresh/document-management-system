"""sales_invoice_signatures

Revision ID: u1v2w3x4y5z6
Revises: t1u2v3w4x5y6
Create Date: 2026-11-18 18:30:00.000000

Adds sales_invoice_signatures and temporary_signature_uploads tables for
Module 13 Outbound Sales Invoice signature placement and precision stamping.
Enforces physical boundary constraints and database-level immutability triggers.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'u1v2w3x4y5z6'
down_revision = 't1u2v3w4x5y6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. temporary_signature_uploads table
    op.create_table(
        'temporary_signature_uploads',
        sa.Column('upload_token_hash', sa.String(length=64), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=50), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('aspect_ratio', sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column('width_px', sa.Integer(), nullable=False),
        sa.Column('height_px', sa.Integer(), nullable=False),
        sa.Column('consumed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_temp_sig_uploads_company_id', 'temporary_signature_uploads', ['company_id'])
    op.create_index('ix_temp_sig_uploads_expires_at', 'temporary_signature_uploads', ['expires_at'])

    # 2. sales_invoice_signatures table
    op.create_table(
        'sales_invoice_signatures',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=50), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('page_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('is_pinned_to_last_page', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('x_mm', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('y_mm', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('width_mm', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('height_mm', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id', 'invoice_id'],
            ['invoices.company_id', 'invoices.id'],
            name='fk_sales_invoice_signatures_invoice',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['company_id'],
            ['companies.id'],
            name='fk_sales_invoice_signatures_company',
            ondelete='RESTRICT'
        ),
        sa.CheckConstraint('page_number >= 1', name='chk_sig_page_number'),
        sa.CheckConstraint('x_mm >= 0', name='chk_sig_x_mm'),
        sa.CheckConstraint('y_mm >= 0', name='chk_sig_y_mm'),
        sa.CheckConstraint('width_mm >= 10.0', name='chk_sig_width_mm'),
        sa.CheckConstraint('height_mm >= 5.0', name='chk_sig_height_mm'),
        sa.CheckConstraint('(x_mm + width_mm) <= 210.0', name='chk_sig_x_boundary'),
        sa.CheckConstraint('(y_mm + height_mm) <= 297.0', name='chk_sig_y_boundary'),
    )
    op.create_index('ix_sales_invoice_signatures_company_invoice', 'sales_invoice_signatures', ['company_id', 'invoice_id'])

    # 3. Immutability Trigger on sales_invoice_signatures
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_fn_enforce_signature_immutability()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(50);
            v_kind VARCHAR(50);
            v_inv_id INTEGER;
        BEGIN
            v_inv_id := COALESCE(NEW.invoice_id, OLD.invoice_id);

            SELECT status, kind INTO v_status, v_kind
            FROM invoices
            WHERE id = v_inv_id;

            IF v_status IN ('approved', 'cancelled') THEN
                RAISE EXCEPTION 'Cannot modify or delete signatures on an approved or cancelled invoice (ID: %, status: %).',
                    v_inv_id, v_status;
            END IF;

            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_sales_invoice_signatures_immutability
        BEFORE INSERT OR UPDATE OR DELETE ON sales_invoice_signatures
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_enforce_signature_immutability();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_sales_invoice_signatures_immutability ON sales_invoice_signatures;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_enforce_signature_immutability();")
    op.drop_table('sales_invoice_signatures')
    op.drop_table('temporary_signature_uploads')
