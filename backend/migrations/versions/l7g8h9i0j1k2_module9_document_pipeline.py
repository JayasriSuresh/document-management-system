"""module9_document_pipeline

Revision ID: l7g8h9i0j1k2
Revises: k6f7g8h9i0j1
Create Date: 2026-11-10 12:00:00.000000

Module 9 — Document Pipeline Hardening and Durable Job Queue:
- documents: sha256, page_count, error_code, restored_at, restored_by
- documents: partial unique index (company_id, sha256) WHERE deleted_at IS NULL
- processing_jobs: durable PostgreSQL-backed queue table with skip-locked claiming and active-job unique constraint
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'l7g8h9i0j1k2'
down_revision: Union[str, Sequence[str], None] = 'k6f7g8h9i0j1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add new columns to documents
    conn.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64) NULL,
        ADD COLUMN IF NOT EXISTS page_count INTEGER NULL,
        ADD COLUMN IF NOT EXISTS error_code VARCHAR(64) NULL,
        ADD COLUMN IF NOT EXISTS restored_at TIMESTAMP WITHOUT TIME ZONE NULL,
        ADD COLUMN IF NOT EXISTS restored_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL;
    """))

    # 2. Indexes on documents
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_documents_sha256 ON documents(sha256);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_company_sha256_active
        ON documents (company_id, sha256)
        WHERE deleted_at IS NULL AND sha256 IS NOT NULL;
    """))

    # 3. Create processing_jobs table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id BIGSERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER NOT NULL,
            job_type VARCHAR(50) NOT NULL DEFAULT 'ocr_extraction',
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            run_after TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            locked_by VARCHAR(128) NULL,
            locked_at TIMESTAMP WITHOUT TIME ZONE NULL,
            last_error TEXT NULL,
            error_code VARCHAR(64) NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            completed_at TIMESTAMP WITHOUT TIME ZONE NULL
        );
    """))

    # 4. Indexes and constraints on processing_jobs
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_processing_jobs_active_doc
        ON processing_jobs (document_id, job_type)
        WHERE status IN ('pending', 'running');

        CREATE INDEX IF NOT EXISTS ix_processing_jobs_claim
        ON processing_jobs (status, run_after);

        CREATE INDEX IF NOT EXISTS ix_processing_jobs_company_branch
        ON processing_jobs (company_id, branch_id);

        CREATE INDEX IF NOT EXISTS ix_processing_jobs_document_id
        ON processing_jobs (document_id);

        CREATE INDEX IF NOT EXISTS ix_processing_jobs_status
        ON processing_jobs (status);
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop processing_jobs
    conn.execute(text("DROP TABLE IF EXISTS processing_jobs CASCADE;"))

    # Drop documents partial index and columns
    conn.execute(text("""
        DROP INDEX IF EXISTS uq_documents_company_sha256_active;
        DROP INDEX IF EXISTS ix_documents_sha256;
        ALTER TABLE documents
        DROP COLUMN IF EXISTS sha256,
        DROP COLUMN IF EXISTS page_count,
        DROP COLUMN IF EXISTS error_code,
        DROP COLUMN IF EXISTS restored_at,
        DROP COLUMN IF EXISTS restored_by;
    """))
