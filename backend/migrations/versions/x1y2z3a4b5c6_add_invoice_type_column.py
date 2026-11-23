"""add_invoice_type_column

Revision ID: x1y2z3a4b5c6
Revises: w1x2y3z4a5b6
Create Date: 2026-11-20 17:55:00.000000

Adds invoice_type column to documents and invoices tables with default 'Tax Invoice'
and creates lookup indexes.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'x1y2z3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'w1x2y3z4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS invoice_type VARCHAR(64) DEFAULT 'Tax Invoice';
        ALTER TABLE invoices ADD COLUMN IF NOT EXISTS invoice_type VARCHAR(64) DEFAULT 'Tax Invoice';
        UPDATE documents SET invoice_type = 'Tax Invoice' WHERE invoice_type IS NULL;
        UPDATE invoices SET invoice_type = 'Tax Invoice' WHERE invoice_type IS NULL;
        CREATE INDEX IF NOT EXISTS ix_documents_invoice_type ON documents(invoice_type);
        CREATE INDEX IF NOT EXISTS ix_invoices_invoice_type ON invoices(invoice_type);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DROP INDEX IF EXISTS ix_documents_invoice_type;
        DROP INDEX IF EXISTS ix_invoices_invoice_type;
        ALTER TABLE documents DROP COLUMN IF EXISTS invoice_type;
        ALTER TABLE invoices DROP COLUMN IF EXISTS invoice_type;
    """))
