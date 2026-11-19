"""module6_mfa

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-11-04 14:48:00.000000

Implements Module 6: Multi-Factor Authentication (TOTP & Recovery Codes)
- Table: user_mfa (supports both users and master_admins via mutually exclusive check)
- Table: mfa_recovery_codes (hashed single-use codes)
- Table: platform_settings (platform-wide MFA policies)
- Column: companies.mfa_required_for_all (company-level MFA policy)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'h3c4d5e6f7g8'
down_revision: Union[str, Sequence[str], None] = 'g2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add mfa_required_for_all to companies
    conn.execute(text("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS mfa_required_for_all BOOLEAN NOT NULL DEFAULT FALSE;
    """))

    # 2. Create user_mfa table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_mfa (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE,
            master_admin_id INTEGER NULL REFERENCES master_admins(id) ON DELETE CASCADE,
            encrypted_secret TEXT NOT NULL,
            enabled_at TIMESTAMP WITHOUT TIME ZONE NULL,
            last_used_step BIGINT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_user_mfa_user_id UNIQUE (user_id),
            CONSTRAINT uq_user_mfa_master_admin_id UNIQUE (master_admin_id),
            CONSTRAINT chk_user_mfa_exclusive_identity CHECK (
                (user_id IS NOT NULL AND master_admin_id IS NULL) OR
                (user_id IS NULL AND master_admin_id IS NOT NULL)
            )
        );
        CREATE INDEX IF NOT EXISTS ix_user_mfa_user_id ON user_mfa (user_id);
        CREATE INDEX IF NOT EXISTS ix_user_mfa_master_admin_id ON user_mfa (master_admin_id);
    """))

    # 3. Create mfa_recovery_codes table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS mfa_recovery_codes (
            id SERIAL PRIMARY KEY,
            user_mfa_id INTEGER NOT NULL REFERENCES user_mfa(id) ON DELETE CASCADE,
            code_hash VARCHAR(128) NOT NULL,
            used_at TIMESTAMP WITHOUT TIME ZONE NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_mfa_recovery_codes_user_mfa_id ON mfa_recovery_codes (user_mfa_id);
        CREATE INDEX IF NOT EXISTS ix_mfa_recovery_codes_code_hash ON mfa_recovery_codes (code_hash);
    """))

    # 4. Create platform_settings table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS platform_settings (
            id SERIAL PRIMARY KEY,
            key VARCHAR(100) UNIQUE NOT NULL,
            value JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_by INTEGER NULL REFERENCES master_admins(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS ix_platform_settings_key ON platform_settings (key);
    """))

    # 5. Seed default platform MFA policy if not present
    conn.execute(text("""
        INSERT INTO platform_settings (key, value)
        VALUES ('mfa_policy', '{"enforce_master_admin": false, "enforce_company_admin": false, "enforce_all": false}'::jsonb)
        ON CONFLICT (key) DO NOTHING;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS mfa_recovery_codes CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS user_mfa CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS platform_settings CASCADE;"))
    conn.execute(text("ALTER TABLE companies DROP COLUMN IF EXISTS mfa_required_for_all;"))
