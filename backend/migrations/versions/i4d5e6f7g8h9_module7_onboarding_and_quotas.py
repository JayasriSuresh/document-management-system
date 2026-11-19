"""module7_onboarding_and_quotas

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2026-11-05 17:30:00.000000

Implements Module 7:
- Table: company_onboardings
- Table: ai_usage_ledger
- Columns on companies: max_branches, max_users, storage_limit_bytes, monthly_ai_budget_cents, ai_budget_spent_cents
- Column on users: mobile
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'i4d5e6f7g8h9'
down_revision: Union[str, Sequence[str], None] = 'h3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add mobile to users
    conn.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS mobile VARCHAR(32) NULL;
    """))

    # 2. Add quota fields to companies
    conn.execute(text("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS max_branches INTEGER NOT NULL DEFAULT 5,
        ADD COLUMN IF NOT EXISTS max_users INTEGER NOT NULL DEFAULT 20,
        ADD COLUMN IF NOT EXISTS storage_limit_bytes BIGINT NOT NULL DEFAULT 5368709120,
        ADD COLUMN IF NOT EXISTS monthly_ai_budget_cents INTEGER NOT NULL DEFAULT 2500,
        ADD COLUMN IF NOT EXISTS ai_budget_spent_cents INTEGER NOT NULL DEFAULT 0;
    """))

    # 3. Create enum onboardingstatus if not exists
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'onboardingstatus') THEN
                CREATE TYPE onboardingstatus AS ENUM (
                    'pending_submission',
                    'submitted',
                    'changes_requested',
                    'approved',
                    'rejected'
                );
            END IF;
        END$$;
    """))

    # 4. Create company_onboardings table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_onboardings (
            id SERIAL PRIMARY KEY,
            token VARCHAR(64) UNIQUE NOT NULL,
            status onboardingstatus NOT NULL DEFAULT 'pending_submission',
            initial_company_name VARCHAR(255) NOT NULL,
            contact_name VARCHAR(255) NOT NULL,
            contact_email VARCHAR(255) NOT NULL,
            created_by_admin_id INTEGER NULL REFERENCES master_admins(id) ON DELETE SET NULL,
            legal_company_name VARCHAR(255) NULL,
            trade_name VARCHAR(255) NULL,
            business_type VARCHAR(100) NULL,
            business_description TEXT NULL,
            year_of_establishment VARCHAR(32) NULL,
            company_website VARCHAR(255) NULL,
            pan_number VARCHAR(32) NULL,
            gstin VARCHAR(32) NULL,
            gst_type VARCHAR(64) NULL,
            cin VARCHAR(32) NULL,
            llpin VARCHAR(32) NULL,
            udyam_number VARCHAR(64) NULL,
            tan VARCHAR(32) NULL,
            address_line1 VARCHAR(255) NULL,
            address_line2 VARCHAR(255) NULL,
            city VARCHAR(100) NULL,
            state VARCHAR(100) NULL,
            district VARCHAR(100) NULL,
            pincode VARCHAR(20) NULL,
            country VARCHAR(100) NULL DEFAULT 'India',
            auth_contact_name VARCHAR(255) NULL,
            auth_contact_designation VARCHAR(100) NULL,
            auth_contact_email VARCHAR(255) NULL,
            auth_contact_mobile VARCHAR(32) NULL,
            auth_contact_alternate_mobile VARCHAR(32) NULL,
            has_multiple_branches BOOLEAN NULL DEFAULT FALSE,
            branch_details JSONB NULL DEFAULT '[]'::jsonb,
            admin_name VARCHAR(255) NULL,
            admin_email VARCHAR(255) NULL,
            admin_password_hash VARCHAR(255) NULL,
            admin_mobile VARCHAR(32) NULL,
            admin_designation VARCHAR(100) NULL,
            primary_document_types JSONB NULL DEFAULT '[]'::jsonb,
            expected_monthly_volume VARCHAR(64) NULL,
            languages JSONB NULL DEFAULT '[]'::jsonb,
            timezone VARCHAR(64) NULL DEFAULT 'Asia/Kolkata',
            currency VARCHAR(32) NULL DEFAULT 'INR',
            uploaded_documents JSONB NULL DEFAULT '{}'::jsonb,
            review_comments TEXT NULL,
            review_history JSONB NULL DEFAULT '[]'::jsonb,
            company_id INTEGER NULL REFERENCES companies(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            submitted_at TIMESTAMP WITHOUT TIME ZONE NULL,
            reviewed_at TIMESTAMP WITHOUT TIME ZONE NULL
        );
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_company_onboardings_token ON company_onboardings(token);
        CREATE INDEX IF NOT EXISTS ix_company_onboardings_status ON company_onboardings(status);
        CREATE INDEX IF NOT EXISTS ix_company_onboardings_contact_email ON company_onboardings(contact_email);
    """))

    # 5. Create ai_usage_ledger table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_usage_ledger (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER NULL REFERENCES branches(id) ON DELETE SET NULL,
            provider VARCHAR(50) NOT NULL,
            model VARCHAR(100) NOT NULL,
            operation VARCHAR(50) NOT NULL,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_cents INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(32) NOT NULL DEFAULT 'success',
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_ai_usage_ledger_company_id ON ai_usage_ledger(company_id);
        CREATE INDEX IF NOT EXISTS ix_ai_usage_ledger_created_at ON ai_usage_ledger(created_at);
        CREATE INDEX IF NOT EXISTS ix_ai_usage_ledger_company_created ON ai_usage_ledger(company_id, created_at);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS ai_usage_ledger CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS company_onboardings CASCADE;"))
    conn.execute(text("""
        ALTER TABLE companies
        DROP COLUMN IF EXISTS max_branches,
        DROP COLUMN IF EXISTS max_users,
        DROP COLUMN IF EXISTS storage_limit_bytes,
        DROP COLUMN IF EXISTS monthly_ai_budget_cents,
        DROP COLUMN IF EXISTS ai_budget_spent_cents;
    """))
    conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS mobile;"))

