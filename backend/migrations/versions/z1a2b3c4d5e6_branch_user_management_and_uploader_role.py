"""branch_user_management_and_uploader_role

Revision ID: z1a2b3c4d5e6
Revises: y1z2a3b4c5d6
Create Date: 2026-11-23 16:30:00.000000

Adds UPLOADER value to PostgreSQL enum userrole if not already present.
Ensures seamless enum support for UPLOADER role assignments.
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'z1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'y1z2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'UPLOADER'"))


def downgrade() -> None:
    # In PostgreSQL, enum values cannot be dropped without recreating the enum.
    # Leaving the enum value intact on downgrade is standard and safe.
    pass
