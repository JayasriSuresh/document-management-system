"""branch_extended_fields

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2026-11-06 15:35:00.000000

Adds missing extended branch profile columns to branches table:
- branch_type, branch_email, branch_contact_number
- address_line1, address_line2, city, district, state, pincode, country
- gst_registered, gstin, gst_type, status
- Drops legacy global unique constraint tenants_name_key on branch name, replaces with per-company unique constraint
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'j5e6f7g8h9i0'
down_revision: Union[str, Sequence[str], None] = 'i4d5e6f7g8h9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add branch detail columns
    conn.execute(text("""
        ALTER TABLE branches
        ADD COLUMN IF NOT EXISTS branch_type VARCHAR(100) NULL DEFAULT 'Branch',
        ADD COLUMN IF NOT EXISTS branch_email VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS branch_contact_number VARCHAR(32) NULL,
        ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS address_line2 VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS city VARCHAR(100) NULL,
        ADD COLUMN IF NOT EXISTS district VARCHAR(100) NULL,
        ADD COLUMN IF NOT EXISTS state VARCHAR(100) NULL,
        ADD COLUMN IF NOT EXISTS pincode VARCHAR(20) NULL,
        ADD COLUMN IF NOT EXISTS country VARCHAR(100) NULL DEFAULT 'India',
        ADD COLUMN IF NOT EXISTS gst_registered BOOLEAN NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS gstin VARCHAR(32) NULL,
        ADD COLUMN IF NOT EXISTS gst_type VARCHAR(64) NULL,
        ADD COLUMN IF NOT EXISTS status VARCHAR(32) NULL DEFAULT 'active';
    """))

    # 2. Drop legacy global unique name constraint if present, and add per-company constraint
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'tenants_name_key'
            ) THEN
                ALTER TABLE branches DROP CONSTRAINT tenants_name_key;
            END IF;
        END$$;
    """))

    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_branches_company_id_name'
            ) THEN
                ALTER TABLE branches ADD CONSTRAINT uq_branches_company_id_name UNIQUE (company_id, name);
            END IF;
        END$$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE branches
        DROP COLUMN IF EXISTS branch_type,
        DROP COLUMN IF EXISTS branch_email,
        DROP COLUMN IF EXISTS branch_contact_number,
        DROP COLUMN IF EXISTS address_line1,
        DROP COLUMN IF EXISTS address_line2,
        DROP COLUMN IF EXISTS city,
        DROP COLUMN IF EXISTS district,
        DROP COLUMN IF EXISTS state,
        DROP COLUMN IF EXISTS pincode,
        DROP COLUMN IF EXISTS country,
        DROP COLUMN IF EXISTS gst_registered,
        DROP COLUMN IF EXISTS gstin,
        DROP COLUMN IF EXISTS gst_type,
        DROP COLUMN IF EXISTS status;
    """))

