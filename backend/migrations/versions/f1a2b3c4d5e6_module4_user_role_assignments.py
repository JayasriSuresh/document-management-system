"""module4_user_role_assignments

Revision ID: f1a2b3c4d5e6
Revises: e8a1d2f3c4b5
Create Date: 2026-11-03 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e8a1d2f3c4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create user_role_assignments table idempotently
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_role_assignments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(64) NOT NULL,
            scope_type VARCHAR(32) NOT NULL,
            scope_id INTEGER NOT NULL,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            CONSTRAINT uq_user_role_scope UNIQUE (user_id, role, scope_type, scope_id),
            CONSTRAINT chk_role_assignment_scope_type CHECK (scope_type IN ('company', 'branch'))
        );

        CREATE INDEX IF NOT EXISTS ix_user_role_assignments_user_id ON user_role_assignments (user_id);
        CREATE INDEX IF NOT EXISTS ix_user_role_assignments_role ON user_role_assignments (role);
        CREATE INDEX IF NOT EXISTS ix_user_role_assignments_user_role ON user_role_assignments (user_id, role);
        CREATE INDEX IF NOT EXISTS ix_user_role_assignments_scope ON user_role_assignments (scope_type, scope_id);
    """))

    # 2. Transactional migration of existing user roles into user_role_assignments
    # For GLOBAL_ADMIN: scope_type = 'company', scope_id = company_id
    # For ADMIN: scope_type = 'branch', scope_id = branch_id
    # For STAFF: scope_type = 'branch', scope_id = branch_id (also alias to UPLOADER)
    conn.execute(text("""
        DO $$
        DECLARE
            u RECORD;
            b_comp INTEGER;
        BEGIN
            FOR u IN SELECT id, role::text as role, company_id, branch_id FROM users LOOP
                -- Verify branch belongs to user's company
                SELECT company_id INTO b_comp FROM branches WHERE id = u.branch_id;
                IF b_comp IS NULL OR b_comp != u.company_id THEN
                    RAISE EXCEPTION 'User % has invalid branch assignment: branch % does not belong to company %',
                        u.id, u.branch_id, u.company_id;
                END IF;

                IF u.role = 'GLOBAL_ADMIN' THEN
                    INSERT INTO user_role_assignments (user_id, role, scope_type, scope_id, created_at)
                    VALUES (u.id, 'GLOBAL_ADMIN', 'company', u.company_id, NOW())
                    ON CONFLICT (user_id, role, scope_type, scope_id) DO NOTHING;
                ELSIF u.role = 'ADMIN' THEN
                    INSERT INTO user_role_assignments (user_id, role, scope_type, scope_id, created_at)
                    VALUES (u.id, 'ADMIN', 'branch', u.branch_id, NOW())
                    ON CONFLICT (user_id, role, scope_type, scope_id) DO NOTHING;
                ELSIF u.role = 'STAFF' THEN
                    -- Insert both STAFF and UPLOADER for complete backward and forward compatibility
                    INSERT INTO user_role_assignments (user_id, role, scope_type, scope_id, created_at)
                    VALUES (u.id, 'STAFF', 'branch', u.branch_id, NOW())
                    ON CONFLICT (user_id, role, scope_type, scope_id) DO NOTHING;

                    INSERT INTO user_role_assignments (user_id, role, scope_type, scope_id, created_at)
                    VALUES (u.id, 'UPLOADER', 'branch', u.branch_id, NOW())
                    ON CONFLICT (user_id, role, scope_type, scope_id) DO NOTHING;
                END IF;
            END LOOP;
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS user_role_assignments;"))

