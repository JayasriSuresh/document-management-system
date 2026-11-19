"""module10_ai_provider_layer

Revision ID: m1n2o3p4q5r6
Revises: l7g8h9i0j1k2
Create Date: 2026-11-10 14:40:00.000000

Module 10 – AI Provider Layer (Gemini, GPT, Claude):
- ai_providers: platform-level provider catalogue and model allow-lists
- company_ai_settings: company allowed providers and defaults
- company_ai_consents: explicit provider-specific company consent records
- branch_ai_configs: branch-level operation mapping (read/generate) with primary/fallback
- ai_credentials: encrypted API credentials with write-only masking
- ai_processing_logs: detailed attempt-level execution logs with token and cost tracking
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'm1n2o3p4q5r6'
down_revision: Union[str, Sequence[str], None] = 'l7g8h9i0j1k2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. ai_providers
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_providers (
            id SERIAL PRIMARY KEY,
            provider_key VARCHAR(32) NOT NULL UNIQUE,
            display_name VARCHAR(64) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            model_allow_list JSONB NOT NULL DEFAULT '[]'::jsonb,
            supported_operations JSONB NOT NULL DEFAULT '["read", "generate"]'::jsonb,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_ai_providers_key ON ai_providers(provider_key);
    """))

    # Seed initial platform providers
    conn.execute(text("""
        INSERT INTO ai_providers (provider_key, display_name, is_enabled, model_allow_list, supported_operations)
        VALUES
        ('gemini', 'Google Gemini', true, '["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-3.6-flash"]'::jsonb, '["read", "generate"]'::jsonb),
        ('openai', 'OpenAI GPT', true, '["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"]'::jsonb, '["read", "generate"]'::jsonb),
        ('anthropic', 'Anthropic Claude', true, '["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"]'::jsonb, '["read", "generate"]'::jsonb)
        ON CONFLICT (provider_key) DO NOTHING;
    """))

    # 2. company_ai_settings
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_ai_settings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE UNIQUE,
            allowed_providers JSONB NOT NULL DEFAULT '["gemini", "openai", "anthropic"]'::jsonb,
            default_read_provider VARCHAR(32) NULL,
            default_read_model VARCHAR(64) NULL,
            default_generate_provider VARCHAR(32) NULL,
            default_generate_model VARCHAR(64) NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_company_ai_settings_comp ON company_ai_settings(company_id);
    """))

    # 3. company_ai_consents
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_ai_consents (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            provider_key VARCHAR(32) NOT NULL,
            is_consented BOOLEAN NOT NULL DEFAULT false,
            consented_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
            consented_at TIMESTAMP WITHOUT TIME ZONE NULL,
            policy_version VARCHAR(32) NOT NULL DEFAULT '1.0',
            revoked_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
            revoked_at TIMESTAMP WITHOUT TIME ZONE NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_company_ai_consents_provider
        ON company_ai_consents (company_id, provider_key);
        CREATE INDEX IF NOT EXISTS ix_company_ai_consents_provider ON company_ai_consents(provider_key);
    """))

    # 4. branch_ai_configs
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS branch_ai_configs (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
            operation VARCHAR(32) NOT NULL,
            primary_provider VARCHAR(32) NOT NULL,
            primary_model VARCHAR(64) NOT NULL,
            fallback_provider VARCHAR(32) NULL,
            fallback_model VARCHAR(64) NULL,
            max_retries INTEGER NOT NULL DEFAULT 2,
            timeout_seconds INTEGER NOT NULL DEFAULT 30,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_ai_configs_op
        ON branch_ai_configs (company_id, branch_id, operation);
        CREATE INDEX IF NOT EXISTS ix_branch_ai_configs_branch ON branch_ai_configs(branch_id);
    """))

    # 5. ai_credentials
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_credentials (
            id SERIAL PRIMARY KEY,
            provider_key VARCHAR(32) NOT NULL,
            scope_type VARCHAR(32) NOT NULL,
            scope_id INTEGER NULL,
            encrypted_key TEXT NOT NULL,
            key_version INTEGER NOT NULL DEFAULT 1,
            masked_key VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            last_verified_at TIMESTAMP WITHOUT TIME ZONE NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_credentials_scope
        ON ai_credentials (provider_key, scope_type, COALESCE(scope_id, 0));
        CREATE INDEX IF NOT EXISTS ix_ai_credentials_provider ON ai_credentials(provider_key);
    """))

    # 6. ai_processing_logs
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_processing_logs (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER NULL REFERENCES branches(id) ON DELETE SET NULL,
            document_id INTEGER NULL REFERENCES documents(id) ON DELETE SET NULL,
            job_id BIGINT NULL REFERENCES processing_jobs(id) ON DELETE SET NULL,
            operation VARCHAR(32) NOT NULL,
            provider VARCHAR(32) NOT NULL,
            model VARCHAR(64) NOT NULL,
            is_fallback BOOLEAN NOT NULL DEFAULT false,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_cents INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            success BOOLEAN NOT NULL DEFAULT true,
            error_code VARCHAR(64) NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_ai_processing_logs_comp_created
        ON ai_processing_logs (company_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_ai_processing_logs_branch
        ON ai_processing_logs (branch_id);
        CREATE INDEX IF NOT EXISTS ix_ai_processing_logs_doc
        ON ai_processing_logs (document_id);
        CREATE INDEX IF NOT EXISTS ix_ai_processing_logs_job
        ON ai_processing_logs (job_id);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS ai_processing_logs CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS ai_credentials CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS branch_ai_configs CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS company_ai_consents CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS company_ai_settings CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS ai_providers CASCADE;"))
