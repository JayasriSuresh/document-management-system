"""centralized_master_admin_ai_management

Revision ID: a2b3c4d5e6f7
Revises: z1a2b3c4d5e6
Create Date: 2026-11-24 15:05:00.000000

Objective:
- Establish Master Admin centralized control over AI models and company assignments.
- Create ai_models catalogue table with capability definitions.
- Create company_ai_model_assignments table for task-based company model assignments.
- Create company_ai_requests table for company model request workflow.
- Add is_ai_enabled to company_ai_settings.
- Seed foundational model catalogue and migrate existing company defaults safely.
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'z1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add is_ai_enabled to company_ai_settings
    conn.execute(text("""
        ALTER TABLE company_ai_settings 
        ADD COLUMN IF NOT EXISTS is_ai_enabled BOOLEAN NOT NULL DEFAULT TRUE;
    """))

    # 2. Create ai_models catalogue
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_models (
            id SERIAL PRIMARY KEY,
            provider_key VARCHAR(32) NOT NULL,
            model_id VARCHAR(64) NOT NULL,
            display_name VARCHAR(64) NOT NULL,
            capabilities JSON NOT NULL DEFAULT '["ocr", "extraction", "generation"]'::json,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            metadata_json JSON NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_models_provider_model 
        ON ai_models (provider_key, model_id);
        CREATE INDEX IF NOT EXISTS ix_ai_models_provider ON ai_models(provider_key);
        CREATE INDEX IF NOT EXISTS ix_ai_models_is_active ON ai_models(is_active);
    """))

    # 3. Create company_ai_model_assignments
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_ai_model_assignments (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            task_type VARCHAR(32) NOT NULL,
            provider_key VARCHAR(32) NOT NULL,
            model_id VARCHAR(64) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_by INTEGER REFERENCES master_admins(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_company_ai_model_assignments_task
        ON company_ai_model_assignments (company_id, task_type);
        CREATE INDEX IF NOT EXISTS ix_company_ai_model_assignments_company
        ON company_ai_model_assignments(company_id);
    """))

    # 4. Create company_ai_requests
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_ai_requests (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            provider_key VARCHAR(32) NOT NULL,
            model_id VARCHAR(64) NOT NULL,
            task_type VARCHAR(32) NOT NULL,
            reason TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            decision_by INTEGER REFERENCES master_admins(id) ON DELETE SET NULL,
            decision_reason TEXT NULL,
            decided_at TIMESTAMP WITHOUT TIME ZONE NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_company_ai_requests_company_status
        ON company_ai_requests(company_id, status);
        CREATE INDEX IF NOT EXISTS ix_company_ai_requests_status
        ON company_ai_requests(status);
    """))

    # 5. Seed foundational AI model catalogue
    conn.execute(text("""
        INSERT INTO ai_models (provider_key, model_id, display_name, capabilities, is_active)
        VALUES
            ('gemini', 'gemini-2.0-flash', 'Gemini 2.0 Flash', '["ocr", "extraction", "generation"]'::json, true),
            ('gemini', 'gemini-1.5-flash', 'Gemini 1.5 Flash', '["ocr", "extraction", "generation"]'::json, true),
            ('gemini', 'gemini-1.5-pro', 'Gemini 1.5 Pro', '["ocr", "extraction", "generation"]'::json, true),
            ('openai', 'gpt-4o', 'GPT-4o', '["ocr", "extraction", "generation"]'::json, true),
            ('openai', 'gpt-4o-mini', 'GPT-4o Mini', '["ocr", "extraction", "generation"]'::json, true),
            ('openai', 'gpt-4-turbo', 'GPT-4 Turbo', '["ocr", "extraction", "generation"]'::json, true),
            ('anthropic', 'claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet', '["ocr", "extraction", "generation"]'::json, true),
            ('anthropic', 'claude-3-5-haiku-20241022', 'Claude 3.5 Haiku', '["ocr", "extraction", "generation"]'::json, true)
        ON CONFLICT (provider_key, model_id) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            capabilities = EXCLUDED.capabilities,
            is_active = EXCLUDED.is_active;
    """))

    # 6. Migrate existing company defaults safely into company_ai_model_assignments
    conn.execute(text("""
        INSERT INTO company_ai_model_assignments (company_id, task_type, provider_key, model_id, is_enabled)
        SELECT 
            c.id, 
            'ocr', 
            COALESCE(s.default_read_provider, 'gemini'), 
            COALESCE(s.default_read_model, 'gemini-2.0-flash'),
            true
        FROM companies c
        LEFT JOIN company_ai_settings s ON s.company_id = c.id
        ON CONFLICT (company_id, task_type) DO NOTHING;

        INSERT INTO company_ai_model_assignments (company_id, task_type, provider_key, model_id, is_enabled)
        SELECT 
            c.id, 
            'extraction', 
            COALESCE(s.default_read_provider, 'gemini'), 
            COALESCE(s.default_read_model, 'gemini-2.0-flash'),
            true
        FROM companies c
        LEFT JOIN company_ai_settings s ON s.company_id = c.id
        ON CONFLICT (company_id, task_type) DO NOTHING;

        INSERT INTO company_ai_model_assignments (company_id, task_type, provider_key, model_id, is_enabled)
        SELECT 
            c.id, 
            'generation', 
            COALESCE(s.default_generate_provider, 'gemini'), 
            COALESCE(s.default_generate_model, 'gemini-2.0-flash'),
            true
        FROM companies c
        LEFT JOIN company_ai_settings s ON s.company_id = c.id
        ON CONFLICT (company_id, task_type) DO NOTHING;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS company_ai_requests CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS company_ai_model_assignments CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS ai_models CASCADE;"))
    conn.execute(text("ALTER TABLE company_ai_settings DROP COLUMN IF EXISTS is_ai_enabled;"))
