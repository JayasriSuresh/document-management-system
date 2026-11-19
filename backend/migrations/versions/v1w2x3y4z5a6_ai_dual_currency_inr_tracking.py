"""AI Dual Currency INR Tracking and Reconciliation (Module 7 & 10)

Revision ID: v1w2x3y4z5a6
Revises: u1v2w3x4y5z6
Create Date: 2026-11-19 12:35:00.000000

Adds dual-currency columns for Indian Rupees (INR) alongside original USD provider billing:
- companies: reporting_currency, monthly_ai_budget_inr, ai_budget_spent_inr
- ai_usage_ledger: cost_inr, exchange_rate, converted_at, currency
- ai_processing_logs: cost_inr, exchange_rate, converted_at, currency
Backfills existing rows with default 85.00 exchange rate.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = 'v1w2x3y4z5a6'
down_revision = 'u1v2w3x4y5z6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update companies table
    op.add_column(
        'companies',
        sa.Column('reporting_currency', sa.String(length=10), server_default='INR', nullable=False)
    )
    op.add_column(
        'companies',
        sa.Column('monthly_ai_budget_inr', sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column(
        'companies',
        sa.Column('ai_budget_spent_inr', sa.Numeric(precision=12, scale=4), server_default='0.0000', nullable=False)
    )

    # 2. Update ai_usage_ledger table
    op.add_column(
        'ai_usage_ledger',
        sa.Column('cost_inr', sa.Numeric(precision=12, scale=4), server_default='0.0000', nullable=False)
    )
    op.add_column(
        'ai_usage_ledger',
        sa.Column('exchange_rate', sa.Numeric(precision=10, scale=4), server_default='85.0000', nullable=False)
    )
    op.add_column(
        'ai_usage_ledger',
        sa.Column('converted_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'ai_usage_ledger',
        sa.Column('currency', sa.String(length=10), server_default='INR', nullable=False)
    )

    # 3. Update ai_processing_logs table
    op.add_column(
        'ai_processing_logs',
        sa.Column('cost_inr', sa.Numeric(precision=12, scale=4), server_default='0.0000', nullable=False)
    )
    op.add_column(
        'ai_processing_logs',
        sa.Column('exchange_rate', sa.Numeric(precision=10, scale=4), server_default='85.0000', nullable=False)
    )
    op.add_column(
        'ai_processing_logs',
        sa.Column('converted_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'ai_processing_logs',
        sa.Column('currency', sa.String(length=10), server_default='INR', nullable=False)
    )

    # 4. Backfill existing records
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE companies
        SET monthly_ai_budget_inr = ROUND((monthly_ai_budget_cents::numeric / 100.0) * 85.0, 2),
            ai_budget_spent_inr = ROUND((ai_budget_spent_cents::numeric / 100.0) * 85.0, 4),
            reporting_currency = 'INR'
        WHERE monthly_ai_budget_inr IS NULL;
    """))

    conn.execute(text("""
        UPDATE ai_usage_ledger
        SET cost_inr = ROUND((cost_cents::numeric / 100.0) * 85.0, 4),
            exchange_rate = 85.0,
            converted_at = created_at,
            currency = 'INR'
        WHERE cost_inr = 0 AND cost_cents > 0;
    """))

    conn.execute(text("""
        UPDATE ai_processing_logs
        SET cost_inr = ROUND((cost_cents::numeric / 100.0) * 85.0, 4),
            exchange_rate = 85.0,
            converted_at = created_at,
            currency = 'INR'
        WHERE cost_inr = 0 AND cost_cents > 0;
    """))


def downgrade():
    op.drop_column('ai_processing_logs', 'currency')
    op.drop_column('ai_processing_logs', 'converted_at')
    op.drop_column('ai_processing_logs', 'exchange_rate')
    op.drop_column('ai_processing_logs', 'cost_inr')

    op.drop_column('ai_usage_ledger', 'currency')
    op.drop_column('ai_usage_ledger', 'converted_at')
    op.drop_column('ai_usage_ledger', 'exchange_rate')
    op.drop_column('ai_usage_ledger', 'cost_inr')

    op.drop_column('companies', 'ai_budget_spent_inr')
    op.drop_column('companies', 'monthly_ai_budget_inr')
    op.drop_column('companies', 'reporting_currency')
