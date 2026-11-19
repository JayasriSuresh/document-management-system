"""baseline_schema

Revision ID: a39ceb30351a
Revises: 
Create Date: 2026-11-02 12:34:05.422723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a39ceb30351a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: idempotent creation for fresh DB or existing DB."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # 1. tenants
    if 'tenants' not in existing_tables:
        op.create_table(
            'tenants',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name')
        )
        op.create_index(op.f('ix_tenants_id'), 'tenants', ['id'], unique=False)

    # 2. users
    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('role', sa.Enum('GLOBAL_ADMIN', 'ADMIN', 'STAFF', name='userrole'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('email')
        )
        op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # 3. documents
    if 'documents' not in existing_tables:
        op.create_table(
            'documents',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('uploaded_by', sa.Integer(), nullable=False),
            sa.Column('original_filename', sa.String(length=512), nullable=False),
            sa.Column('storage_key', sa.String(length=512), nullable=False),
            sa.Column('mime_type', sa.String(length=128), nullable=False),
            sa.Column('file_size', sa.BigInteger(), nullable=False),
            sa.Column('ocr_text', sa.Text(), nullable=True),
            sa.Column('structured_data', sa.Text(), nullable=True),
            sa.Column('ocr_status', sa.Enum('UPLOADED', 'PROCESSING', 'COMPLETED', 'FAILED', name='ocrstatus'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], ),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
            sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('storage_key')
        )
        op.create_index(op.f('ix_documents_id'), 'documents', ['id'], unique=False)

    # 4. invoices
    if 'invoices' not in existing_tables:
        op.create_table(
            'invoices',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('document_id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('uploaded_by', sa.Integer(), nullable=False),
            sa.Column('invoice_number', sa.String(length=255), nullable=True),
            sa.Column('invoice_date', sa.String(length=255), nullable=True),
            sa.Column('seller_name', sa.String(length=512), nullable=True),
            sa.Column('seller_gstin', sa.String(length=255), nullable=True),
            sa.Column('buyer_name', sa.String(length=512), nullable=True),
            sa.Column('buyer_gstin', sa.String(length=255), nullable=True),
            sa.Column('grand_total', sa.String(length=255), nullable=True),
            sa.Column('currency', sa.String(length=32), nullable=True),
            sa.Column('pdf_filename', sa.String(length=512), nullable=False),
            sa.Column('file_size', sa.BigInteger(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
            sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_invoices_document_id'), 'invoices', ['document_id'], unique=True)
        op.create_index(op.f('ix_invoices_id'), 'invoices', ['id'], unique=False)
        op.create_index(op.f('ix_invoices_invoice_number'), 'invoices', ['invoice_number'], unique=False)
        op.create_index(op.f('ix_invoices_tenant_id'), 'invoices', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_invoices_uploaded_by'), 'invoices', ['uploaded_by'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('invoices')
    op.drop_table('documents')
    op.drop_table('users')
    op.drop_table('tenants')
