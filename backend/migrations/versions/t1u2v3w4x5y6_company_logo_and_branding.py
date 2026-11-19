"""company_logo_and_branding

Revision ID: t1u2v3w4x5y6
Revises: s1t2u3v4w5x6
Create Date: 2026-11-16 18:45:00.000000

Adds logo_url to companies table for corporate branding and sidebar display.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 't1u2v3w4x5y6'
down_revision = 's1t2u3v4w5x6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('companies', sa.Column('logo_url', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('companies', 'logo_url')
