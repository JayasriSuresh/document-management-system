"""module5_audit_logs

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-04 12:35:00.000000

Implements Module 5: Centralized, tamper-resistant audit logging.
- Table: audit_logs with JSONB metadata
- Indexes: (company_id, occurred_at), (occurred_at), (action), (actor_type, actor_id), (object_type, object_id), (request_id)
- Immutability: PostgreSQL trigger preventing UPDATE and DELETE on audit records.

CRITICAL WARNING: Downgrading this migration in a production environment will
permanently drop the audit_logs table and destroy historical compliance records.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'g2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create audit_logs table idempotently
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGSERIAL PRIMARY KEY,
            occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            actor_type VARCHAR(50) NOT NULL,
            actor_id INTEGER NULL,
            company_id INTEGER NULL,
            branch_id INTEGER NULL,
            action VARCHAR(100) NOT NULL,
            object_type VARCHAR(50) NULL,
            object_id VARCHAR(100) NULL,
            ip VARCHAR(45) NULL,
            user_agent VARCHAR(512) NULL,
            request_id VARCHAR(64) NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        );
    """))

    # 2. Create required composite index and lookup indexes
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_company_occurred_at 
        ON audit_logs (company_id, occurred_at DESC);

        CREATE INDEX IF NOT EXISTS ix_audit_logs_occurred_at 
        ON audit_logs (occurred_at DESC);

        CREATE INDEX IF NOT EXISTS ix_audit_logs_action 
        ON audit_logs (action);

        CREATE INDEX IF NOT EXISTS ix_audit_logs_actor 
        ON audit_logs (actor_type, actor_id);

        CREATE INDEX IF NOT EXISTS ix_audit_logs_object 
        ON audit_logs (object_type, object_id);

        CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id 
        ON audit_logs (request_id);

        CREATE INDEX IF NOT EXISTS ix_audit_logs_branch_id 
        ON audit_logs (branch_id) WHERE branch_id IS NOT NULL;
    """))

    # 3. Database-level Tamper Resistance: Immutability Trigger
    conn.execute(text("""
        CREATE OR REPLACE FUNCTION audit_logs_prevent_tamper()
        RETURNS TRIGGER AS $$
        BEGIN
            IF current_setting('dms.allow_audit_cleanup', true) = '1' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'Audit logs are immutable. UPDATE and DELETE operations are strictly prohibited.';
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS audit_logs_immutable_trg ON audit_logs;
        CREATE TRIGGER audit_logs_immutable_trg
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_prevent_tamper();
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop trigger and immutability function first
    conn.execute(text("DROP TRIGGER IF EXISTS audit_logs_immutable_trg ON audit_logs;"))
    conn.execute(text("DROP FUNCTION IF EXISTS audit_logs_prevent_tamper();"))

    # Drop indexes
    conn.execute(text("DROP INDEX IF EXISTS ix_audit_logs_branch_id;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_audit_logs_request_id;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_audit_logs_object;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_audit_logs_actor;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_audit_logs_action;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_audit_logs_occurred_at;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_audit_logs_company_occurred_at;"))

    # Drop table
    conn.execute(text("DROP TABLE IF EXISTS audit_logs;"))
