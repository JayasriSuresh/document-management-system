"""module3_identity_and_portals

Revision ID: e8a1d2f3c4b5
Revises: 6ab3db7907d9
Create Date: 2026-11-02 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'e8a1d2f3c4b5'
down_revision: Union[str, Sequence[str], None] = '6ab3db7907d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create accountstatus enum type idempotently
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'accountstatus') THEN
                CREATE TYPE accountstatus AS ENUM ('active', 'inactive', 'locked');
            END IF;
        END $$;
    """))

    # 2. Create master_admins table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS master_admins (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            status accountstatus NOT NULL DEFAULT 'active',
            token_version INTEGER NOT NULL DEFAULT 1,
            must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            last_login_at TIMESTAMP WITHOUT TIME ZONE
        );
        CREATE INDEX IF NOT EXISTS ix_master_admins_email ON master_admins (email);
        CREATE INDEX IF NOT EXISTS ix_master_admins_status ON master_admins (status);
    """))

    # 3. Add account lifecycle fields to existing users table
    conn.execute(text("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS status accountstatus NOT NULL DEFAULT 'active';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_attempts INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITHOUT TIME ZONE;
    """))

    # 4. Create user_sessions table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id SERIAL PRIMARY KEY,
            identity_type VARCHAR(32) NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            master_admin_id INTEGER REFERENCES master_admins(id) ON DELETE CASCADE,
            token_hash VARCHAR(128) NOT NULL UNIQUE,
            family_id VARCHAR(64) NOT NULL,
            parent_session_id INTEGER,
            user_agent VARCHAR(512),
            ip_address VARCHAR(64),
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            last_used_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            revoked_at TIMESTAMP WITHOUT TIME ZONE,
            revoke_reason VARCHAR(255),
            CONSTRAINT chk_user_session_identity CHECK (
                (identity_type = 'user' AND user_id IS NOT NULL AND master_admin_id IS NULL) OR
                (identity_type = 'master_admin' AND master_admin_id IS NOT NULL AND user_id IS NULL)
            )
        );
        CREATE INDEX IF NOT EXISTS ix_user_sessions_family ON user_sessions (family_id);
        CREATE INDEX IF NOT EXISTS ix_user_sessions_token_hash ON user_sessions (token_hash);
        CREATE INDEX IF NOT EXISTS ix_user_sessions_expires_at ON user_sessions (expires_at);
        CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions (user_id);
        CREATE INDEX IF NOT EXISTS ix_user_sessions_master_admin_id ON user_sessions (master_admin_id);
    """))

    # 5. Create invitations table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS invitations (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER NOT NULL,
            invited_role userrole NOT NULL,
            token_hash VARCHAR(128) NOT NULL UNIQUE,
            invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            accepted_at TIMESTAMP WITHOUT TIME ZONE,
            revoked_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            CONSTRAINT fk_invitations_company_branch FOREIGN KEY (company_id, branch_id)
                REFERENCES branches(company_id, id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_invitations_email ON invitations (email);
        CREATE INDEX IF NOT EXISTS ix_invitations_company_branch ON invitations (company_id, branch_id);
        CREATE INDEX IF NOT EXISTS ix_invitations_token_hash ON invitations (token_hash);
        CREATE INDEX IF NOT EXISTS ix_invitations_expires_at ON invitations (expires_at);
    """))

    # 6. Create password_resets table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id SERIAL PRIMARY KEY,
            identity_type VARCHAR(32) NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            master_admin_id INTEGER REFERENCES master_admins(id) ON DELETE CASCADE,
            token_hash VARCHAR(128) NOT NULL UNIQUE,
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            used_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            requested_ip VARCHAR(64),
            CONSTRAINT chk_password_reset_identity CHECK (
                (identity_type = 'user' AND user_id IS NOT NULL AND master_admin_id IS NULL) OR
                (identity_type = 'master_admin' AND master_admin_id IS NOT NULL AND user_id IS NULL)
            )
        );
        CREATE INDEX IF NOT EXISTS ix_password_resets_token_hash ON password_resets (token_hash);
        CREATE INDEX IF NOT EXISTS ix_password_resets_expires_at ON password_resets (expires_at);
        CREATE INDEX IF NOT EXISTS ix_password_resets_user_id ON password_resets (user_id);
        CREATE INDEX IF NOT EXISTS ix_password_resets_master_admin_id ON password_resets (master_admin_id);
    """))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("DROP TABLE IF EXISTS password_resets CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS invitations CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS user_sessions CASCADE;"))

    conn.execute(text("""
        ALTER TABLE users DROP COLUMN IF EXISTS locked_until;
        ALTER TABLE users DROP COLUMN IF EXISTS failed_attempts;
        ALTER TABLE users DROP COLUMN IF EXISTS must_change_password;
        ALTER TABLE users DROP COLUMN IF EXISTS token_version;
        ALTER TABLE users DROP COLUMN IF EXISTS status;
    """))

    conn.execute(text("DROP TABLE IF EXISTS master_admins CASCADE;"))
    conn.execute(text("DROP TYPE IF EXISTS accountstatus CASCADE;"))
