"""module8_company_profile_fields

Revision ID: k6f7g8h9i0j1
Revises: j5e6f7g8h9i0
Create Date: 2026-11-06 16:00:00.000000

Adds missing company profile fields to companies table and updated_at to branches table:
- companies: display_name, contact_person, contact_email, contact_phone, website, pan
- branches: updated_at
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'k6f7g8h9i0j1'
down_revision: Union[str, Sequence[str], None] = 'j5e6f7g8h9i0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add permitted profile fields to companies
    conn.execute(text("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS display_name VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS contact_person VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(32) NULL,
        ADD COLUMN IF NOT EXISTS website VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS pan VARCHAR(32) NULL;
    """))

    # 2. Add updated_at to branches
    conn.execute(text("""
        ALTER TABLE branches
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE NULL DEFAULT now();
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE companies
        DROP COLUMN IF EXISTS display_name,
        DROP COLUMN IF EXISTS contact_person,
        DROP COLUMN IF EXISTS contact_email,
        DROP COLUMN IF EXISTS contact_phone,
        DROP COLUMN IF EXISTS website,
        DROP COLUMN IF EXISTS pan;
    """))
    conn.execute(text("""
        ALTER TABLE branches
        DROP COLUMN IF EXISTS updated_at;
    """))

