# 🗄️ Database Migrations (Alembic)

DMS uses [Alembic](https://alembic.sqlalchemy.org/) for managing PostgreSQL schema changes safely and reliably across environments.

---

## 📁 Directory Layout

```
backend/
├── alembic.ini              # Alembic config (dynamic database URL from app.config.settings)
└── migrations/
    ├── env.py               # Migration environment wired to SQLAlchemy Base.metadata
    ├── script.py.mako       # Migration template
    └── versions/
        ├── a39ceb30351a_baseline_schema.py   # Baseline migration
        ├── 6ab3db7907d9_company_hierarchy.py # Module 2: Company -> Branch hierarchy
        └── e8a1d2f3c4b5_module3_identity_and_portals.py # Module 3: Portals, MasterAdmin, Sessions, Invites
```

---

## 🚀 Running Migrations

All Alembic commands should be run inside `backend/` with the virtual environment activated:

```bash
cd backend
source venv/bin/activate
```

### 1. Fresh Database Setup

To provision all tables on a fresh database instance:

```bash
alembic upgrade head
```

This runs all revisions up to the latest head. The baseline migration is completely idempotent and sets up:
- `tenants`
- `users`
- `documents`
- `invoices`
- Associated foreign keys, unique constraints, and indexes

### 2. Existing Database Setup

If your database was previously initialized via `create_all` before Alembic was introduced, mark the baseline revision as applied without re-running DDL:

```bash
alembic stamp head
```

To verify the current migration status:

```bash
alembic current
```

---

## 🛠 Creating New Migrations

When you make changes to SQLAlchemy ORM models in `app/models.py`:

```bash
# 1. Autogenerate migration script
alembic revision --autogenerate -m "add_column_name_to_table"

# 2. Inspect the generated file in migrations/versions/
# Verify both upgrade() and downgrade() functions

# 3. Apply the migration
alembic upgrade head
```

---

## ⏪ Rolling Back Migrations

To revert the most recent migration:

```bash
alembic downgrade -1
```

To revert back to baseline:

```bash
alembic downgrade a39ceb30351a
```

---

## 🔒 Production Safety Best Practices

1. **Never commit hardcoded database credentials**: `alembic.ini` pulls `DATABASE_URL` dynamically from `app.config.settings` which respects environment variables and `.env`.
2. **Always test downgrades**: Before deploying to production, verify that `downgrade()` reverses changes cleanly.
3. **CI Validation**: The GitHub Actions CI pipeline runs `alembic upgrade head` against a test PostgreSQL container on every push and pull request.
