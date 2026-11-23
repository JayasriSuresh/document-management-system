"""enterprise_mfa_branch_and_delegation

Revision ID: y1z2a3b4c5d6
Revises: x1y2z3a4b5c6
Create Date: 2026-11-23 13:00:00.000000

Adds allow_branch_mfa_control to companies table.
Adds mfa_required_for_all to branches table with lookup index.
Includes dual-guard protection on downgrade.
"""
import os
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'y1z2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'x1y2z3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE companies ADD COLUMN IF NOT EXISTS allow_branch_mfa_control BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE branches ADD COLUMN IF NOT EXISTS mfa_required_for_all BOOLEAN NOT NULL DEFAULT FALSE;
        CREATE INDEX IF NOT EXISTS ix_branches_mfa_required ON branches(id, mfa_required_for_all);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    active_branch_policies = conn.execute(text("SELECT COUNT(*) FROM branches WHERE mfa_required_for_all = TRUE")).scalar() or 0
    active_delegations = conn.execute(text("SELECT COUNT(*) FROM companies WHERE allow_branch_mfa_control = TRUE")).scalar() or 0

    if (active_branch_policies > 0 or active_delegations > 0) and os.environ.get("FORCE_DROP_MFA_DATA") != "true":
        raise RuntimeError(
            f"ABORTING DOWNGRADE: Configured security data exists! "
            f"Active branch policies: {active_branch_policies}, Active company delegations: {active_delegations}. "
            "Dropping these columns will permanently destroy active enterprise security policies. "
            "Set FORCE_DROP_MFA_DATA=true to override."
        )

    conn.execute(text("""
        DROP INDEX IF EXISTS ix_branches_mfa_required;
        ALTER TABLE branches DROP COLUMN IF EXISTS mfa_required_for_all;
        ALTER TABLE companies DROP COLUMN IF EXISTS allow_branch_mfa_control;
    """))
