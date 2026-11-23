"""allow_duplicate_uploads_with_warning

Revision ID: w1x2y3z4a5b6
Revises: v1w2x3y4z5a6
Create Date: 2026-11-19 15:45:00.000000

Module 9/Frontend Enhancement:
- Replace unique index uq_documents_company_sha256_active on documents(company_id, sha256)
  with non-unique index ix_documents_company_sha256_active to permit user-confirmed duplicate uploads.
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'w1x2y3z4a5b6'
down_revision: Union[str, Sequence[str], None] = 'v1w2x3y4z5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DROP INDEX IF EXISTS uq_documents_company_sha256_active;
        CREATE INDEX IF NOT EXISTS ix_documents_company_sha256_active
        ON documents (company_id, sha256)
        WHERE deleted_at IS NULL AND sha256 IS NOT NULL;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DROP INDEX IF EXISTS ix_documents_company_sha256_active;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_company_sha256_active
        ON documents (company_id, sha256)
        WHERE deleted_at IS NULL AND sha256 IS NOT NULL;
    """))
