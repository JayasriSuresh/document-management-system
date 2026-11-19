"""company_hierarchy

Revision ID: 6ab3db7907d9
Revises: a39ceb30351a
Create Date: 2026-11-02 12:58:55.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '6ab3db7907d9'
down_revision: Union[str, Sequence[str], None] = 'a39ceb30351a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create company status enum & companies table
    conn.execute(text("CREATE TYPE companystatus AS ENUM ('active', 'suspended');")) if False else None
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'companystatus') THEN
                CREATE TYPE companystatus AS ENUM ('active', 'suspended');
            END IF;
        END$$;
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(100) NOT NULL UNIQUE,
            status companystatus NOT NULL DEFAULT 'active',
            gstin VARCHAR(32),
            address TEXT,
            limits JSON,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_companies_id ON companies (id);
        CREATE INDEX IF NOT EXISTS ix_companies_code ON companies (code);
    """))

    # 2. Insert Default Company: Vasanth & Co.
    conn.execute(text("""
        INSERT INTO companies (name, code, status, created_at, updated_at)
        VALUES ('Vasanth & Co.', 'VASANTH_CO', 'active', NOW(), NOW())
        ON CONFLICT (code) DO NOTHING;
    """))

    default_company = conn.execute(text("SELECT id FROM companies WHERE code = 'VASANTH_CO' LIMIT 1")).fetchone()
    default_company_id = default_company[0] if default_company else 1

    # 3. Rename tenants -> branches if tenants exists
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'tenants') 
               AND NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'branches') THEN
                ALTER TABLE tenants RENAME TO branches;
                BEGIN
                    ALTER SEQUENCE tenants_id_seq RENAME TO branches_id_seq;
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;
            END IF;
        END$$;
    """))

    # 4. Modify branches
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'branches' AND column_name = 'company_id') THEN
                ALTER TABLE branches ADD COLUMN company_id INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'branches' AND column_name = 'code') THEN
                ALTER TABLE branches ADD COLUMN code VARCHAR(100);
            END IF;
        END$$;

        UPDATE branches SET company_id = {default_company_id} WHERE company_id IS NULL;
        UPDATE branches SET code = UPPER(REPLACE(name, ' ', '_')) WHERE code IS NULL;

        ALTER TABLE branches ALTER COLUMN company_id SET NOT NULL;
        ALTER TABLE branches ALTER COLUMN code SET NOT NULL;

        ALTER TABLE branches DROP CONSTRAINT IF EXISTS fk_branches_company_id;
        ALTER TABLE branches ADD CONSTRAINT fk_branches_company_id FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE;

        ALTER TABLE branches DROP CONSTRAINT IF EXISTS uq_branches_company_id_id;
        ALTER TABLE branches ADD CONSTRAINT uq_branches_company_id_id UNIQUE (company_id, id);

        ALTER TABLE branches DROP CONSTRAINT IF EXISTS uq_branches_company_id_code;
        ALTER TABLE branches ADD CONSTRAINT uq_branches_company_id_code UNIQUE (company_id, code);
    """))

    # 5. Migrate users
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'tenant_id')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'branch_id') THEN
                ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tenant_id_fkey;
                ALTER TABLE users RENAME COLUMN tenant_id TO branch_id;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'company_id') THEN
                ALTER TABLE users ADD COLUMN company_id INTEGER;
            END IF;
        END$$;

        UPDATE users
        SET company_id = COALESCE((SELECT company_id FROM branches WHERE branches.id = users.branch_id), {default_company_id})
        WHERE company_id IS NULL;

        ALTER TABLE users ALTER COLUMN company_id SET NOT NULL;
        ALTER TABLE users ALTER COLUMN branch_id SET NOT NULL;

        ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_company_id;
        ALTER TABLE users ADD CONSTRAINT fk_users_company_id FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE;

        ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_company_branch;
        ALTER TABLE users ADD CONSTRAINT fk_users_company_branch FOREIGN KEY (company_id, branch_id) REFERENCES branches(company_id, id) ON DELETE CASCADE;

        CREATE INDEX IF NOT EXISTS ix_users_company_branch ON users (company_id, branch_id);
    """))

    # 6. Migrate documents
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'tenant_id')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'branch_id') THEN
                ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_tenant_id_fkey;
                ALTER TABLE documents RENAME COLUMN tenant_id TO branch_id;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'company_id') THEN
                ALTER TABLE documents ADD COLUMN company_id INTEGER;
            END IF;
        END$$;

        UPDATE documents
        SET company_id = COALESCE((SELECT company_id FROM branches WHERE branches.id = documents.branch_id), {default_company_id})
        WHERE company_id IS NULL;

        ALTER TABLE documents ALTER COLUMN company_id SET NOT NULL;
        ALTER TABLE documents ALTER COLUMN branch_id SET NOT NULL;

        ALTER TABLE documents DROP CONSTRAINT IF EXISTS fk_documents_company_id;
        ALTER TABLE documents ADD CONSTRAINT fk_documents_company_id FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE;

        ALTER TABLE documents DROP CONSTRAINT IF EXISTS fk_documents_company_branch;
        ALTER TABLE documents ADD CONSTRAINT fk_documents_company_branch FOREIGN KEY (company_id, branch_id) REFERENCES branches(company_id, id) ON DELETE CASCADE;

        CREATE INDEX IF NOT EXISTS ix_documents_company_branch ON documents (company_id, branch_id);
        CREATE INDEX IF NOT EXISTS ix_documents_company_created ON documents (company_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_documents_company_branch_created ON documents (company_id, branch_id, created_at);
    """))

    # 7. Migrate invoices
    conn.execute(text(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'invoices' AND column_name = 'tenant_id')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'invoices' AND column_name = 'branch_id') THEN
                ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_tenant_id_fkey;
                ALTER TABLE invoices RENAME COLUMN tenant_id TO branch_id;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'invoices' AND column_name = 'company_id') THEN
                ALTER TABLE invoices ADD COLUMN company_id INTEGER;
            END IF;
        END$$;

        UPDATE invoices
        SET company_id = COALESCE((SELECT company_id FROM branches WHERE branches.id = invoices.branch_id), {default_company_id})
        WHERE company_id IS NULL;

        ALTER TABLE invoices ALTER COLUMN company_id SET NOT NULL;
        ALTER TABLE invoices ALTER COLUMN branch_id SET NOT NULL;

        ALTER TABLE invoices DROP CONSTRAINT IF EXISTS fk_invoices_company_id;
        ALTER TABLE invoices ADD CONSTRAINT fk_invoices_company_id FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE;

        ALTER TABLE invoices DROP CONSTRAINT IF EXISTS fk_invoices_company_branch;
        ALTER TABLE invoices ADD CONSTRAINT fk_invoices_company_branch FOREIGN KEY (company_id, branch_id) REFERENCES branches(company_id, id) ON DELETE CASCADE;

        CREATE INDEX IF NOT EXISTS ix_invoices_company_branch ON invoices (company_id, branch_id);
        CREATE INDEX IF NOT EXISTS ix_invoices_company_created ON invoices (company_id, created_at);
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE invoices DROP CONSTRAINT IF EXISTS fk_invoices_company_branch;
        ALTER TABLE invoices DROP CONSTRAINT IF EXISTS fk_invoices_company_id;
        ALTER TABLE invoices DROP COLUMN IF EXISTS company_id;
        ALTER TABLE invoices RENAME COLUMN branch_id TO tenant_id;

        ALTER TABLE documents DROP CONSTRAINT IF EXISTS fk_documents_company_branch;
        ALTER TABLE documents DROP CONSTRAINT IF EXISTS fk_documents_company_id;
        ALTER TABLE documents DROP COLUMN IF EXISTS company_id;
        ALTER TABLE documents RENAME COLUMN branch_id TO tenant_id;

        ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_company_branch;
        ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_company_id;
        ALTER TABLE users DROP COLUMN IF EXISTS company_id;
        ALTER TABLE users RENAME COLUMN branch_id TO tenant_id;

        ALTER TABLE branches DROP CONSTRAINT IF EXISTS fk_branches_company_id;
        ALTER TABLE branches DROP CONSTRAINT IF EXISTS uq_branches_company_id_id;
        ALTER TABLE branches DROP CONSTRAINT IF EXISTS uq_branches_company_id_code;
        ALTER TABLE branches DROP COLUMN IF EXISTS company_id;
        ALTER TABLE branches DROP COLUMN IF EXISTS code;
        ALTER TABLE branches RENAME TO tenants;

        DROP TABLE IF EXISTS companies CASCADE;
    """))
