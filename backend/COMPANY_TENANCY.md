# 🏢 Module 2: Company Tenancy Model (Company → Branch)

## 1. Architectural Overview

Module 2 elevates the Document Management System from a single-tier branch prototype into a true enterprise **Multi-Company Tenancy Architecture**.

### Tenancy Hierarchy

```
┌──────────────────────────────────────────────────────────────┐
│                    Company (Root Tenant)                     │
│               - id, name, code, status (active/suspended)    │
└──────────────────────────────┬───────────────────────────────┘
                               │ 1 : N
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                      Branch (Sub-tenant)                     │
│               - id, company_id, name, code                   │
│               - UNIQUE(company_id, id)                       │
│               - UNIQUE(company_id, code)                     │
└───────────────┬──────────────────────────────┬───────────────┘
                │ 1 : N                        │ 1 : N
                ▼                              ▼
┌───────────────────────────────┐ ┌────────────────────────────┐
│             User              │ │     Document / Invoice     │
│ - id, company_id, branch_id   │ │ - id, company_id, branch_id│
│ - Composite FK to branches    │ │ - Composite FK to branches │
│ - role (GLOBAL_ADMIN /        │ │ - uploaded_by, files, data │
│         ADMIN / STAFF)        │ │                            │
└───────────────────────────────┘ └────────────────────────────┘
```

### Key Architectural Tenets
1. **Primary Tenant Boundary is `Company`:** All access, authorization, search queries, aggregate statistics, and file retrieval are strictly bounded by `company_id`.
2. **Subdivision is `Branch`:** Each company can have multiple branches (e.g. "Chennai", "Mysore"). Branch codes (e.g. `CHENNAI`) are unique *within* a company, allowing different companies to have branches with the same code without collisions.
3. **Hardware / DB-Level Enforcement via Composite Foreign Keys:**
   ```sql
   FOREIGN KEY (company_id, branch_id) REFERENCES branches(company_id, id)
   ```
   PostgreSQL prevents any data corruption or cross-tenant association at the database engine level. A document or user cannot reference a branch belonging to another company.
4. **Zero Cross-Company Data Leakage:**
   - Out-of-company queries, file downloads, or deletion attempts return `404 Not Found` rather than `403 Forbidden`, preventing resource enumeration attacks.
5. **Deterministic Suspension:**
   - Companies can be suspended (`CompanyStatus.SUSPENDED`). All authentication and authenticated API access for users of a suspended company are immediately blocked with `403 Forbidden` (`Company account is suspended`). No tenant data is deleted, and reactivation instantly restores access.

---

## 2. Database Schema & Composite Foreign Keys

### Tables

#### `companies`
| Column | Type | Constraints |
|---|---|---|
| `id` | `INTEGER` | Primary Key, Autoincrement |
| `name` | `VARCHAR(255)` | NOT NULL |
| `code` | `VARCHAR(64)` | NOT NULL, UNIQUE, Indexed |
| `status` | `VARCHAR(32)` / `companystatus` | NOT NULL, DEFAULT `'active'` |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, DEFAULT `NOW()` |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, DEFAULT `NOW()` |

#### `branches` (renamed from prototype `tenants`)
| Column | Type | Constraints |
|---|---|---|
| `id` | `INTEGER` | Primary Key, Autoincrement |
| `company_id` | `INTEGER` | NOT NULL, REFERENCES `companies(id)` ON DELETE CASCADE |
| `name` | `VARCHAR(255)` | NOT NULL |
| `code` | `VARCHAR(64)` | NOT NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, DEFAULT `NOW()` |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, DEFAULT `NOW()` |
| **Constraints** | | `UNIQUE (company_id, id)`<br>`UNIQUE (company_id, code)` |

#### `users`, `documents`, `invoices`
Each entity contains:
- `company_id`: `INTEGER NOT NULL`, REFERENCES `companies(id)` ON DELETE CASCADE
- `branch_id`: `INTEGER NOT NULL`
- `CONSTRAINT fk_..._company_branch FOREIGN KEY (company_id, branch_id) REFERENCES branches(company_id, id) ON DELETE RESTRICT`
- Composite indexes on `(company_id, branch_id)` and entity-specific search/status columns.

---

## 3. AuthContext & Request Lifecycle

Authentication is encapsulated into a typed, immutable dataclass:

```python
# app/context.py
@dataclass(frozen=True)
class AuthContext:
    user_id: int
    company_id: int
    branch_id: int
    role: UserRole
    company_status: CompanyStatus
    email: str = ""
    name: str = ""

    def assert_active_company(self) -> None:
        if self.company_status != CompanyStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company account is suspended. Contact system administrator.",
            )
```

### Request Flow
1. **Token Extraction:** Incoming bearer token in `Authorization: Bearer <token>` or query parameter `?token=<token>` (for secure media streaming).
2. **Signature & Expiration Validation:** PyJWT validates signature, issuer, audience (`dms-portal`), and expiration (`exp`).
3. **Database Hydration:** Resolves user and active company status. If the company is `SUSPENDED`, immediate `403 Forbidden` is returned before executing any route logic.
4. **Context Injection:** `AuthContext` is injected into FastAPI endpoints using standard dependency injection `Depends(get_auth_context)`.

---

## 4. Repository Layer (`app/repositories`)

All direct database queries for tenant data have been migrated into isolated, testable repositories inheriting from `BaseTenantRepository`:

```python
# app/repositories/base.py
class BaseTenantRepository(Generic[T]):
    def __init__(self, db: Session, auth: AuthContext):
        self.db = db
        self.auth = auth

    def base_query(self) -> Query:
        query = self.db.query(self.model_cls).filter(
            self.model_cls.company_id == self.auth.company_id
        )
        # Branch RBAC scoping:
        if self.auth.role == UserRole.STAFF:
            query = query.filter(self.model_cls.branch_id == self.auth.branch_id)
            if hasattr(self.model_cls, "created_at"):
                cutoff = datetime.utcnow() - timedelta(days=30)
                query = query.filter(self.model_cls.created_at >= cutoff)
        elif self.auth.role == UserRole.ADMIN:
            query = query.filter(self.model_cls.branch_id == self.auth.branch_id)
        # GLOBAL_ADMIN sees all branches within self.auth.company_id
        return query
```

### Available Repositories
- **`DocumentRepository`** (`app/repositories/documents.py`):
  - `list_documents(...)`: Multi-tenant filtering, search query matching, OCR status filtering, date range, pagination.
  - `get_by_id(...)`: Scoped retrieval; returns `None` for cross-company IDs (translated to `404`).
  - `create_document(...)`: Automatically binds `company_id` and `branch_id` from `AuthContext`.
  - `soft_delete(...)`: Enforces RBAC permissions (`ADMIN` or `GLOBAL_ADMIN` only) and company scoping.
- **`InvoiceRepository`** (`app/repositories/invoices.py`):
  - `list_invoices(...)`: Company-scoped invoice search and pagination.
  - `get_by_id(...)`: Scoped lookup.
  - `sync_stored_invoices(...)`: Scans storage, ingests PDF invoices with company metadata.
- **`UserRepository`** (`app/repositories/users.py`):
  - User lookup by credentials and ID scoped by company.
- **`CompanyRepository` & `BranchRepository`** (`app/repositories/companies.py`):
  - Company lifecycle (`suspend()`, `activate()`).
  - Branch provisioning and code uniqueness validation.

---

## 5. Backward Compatibility & Module 1 Preservation

To ensure 100% backward compatibility for all existing frontend components and scripts:
1. **Model Aliases & Properties:**
   ```python
   # app/models.py
   Tenant = Branch

   class User(Base):
       @property
       def tenant_id(self) -> int:
           return self.branch_id
   ```
2. **Schema Dual-Support:**
   - Schemas return both `company_id`, `company_name`, `branch_id`, `branch_name` AND `tenant_id`, `tenant_name`.
3. **Implicit Company on Frontend:**
   - Existing users log in with their email and password; their `company_id` and `branch_id` are transparently embedded in the JWT claims and loaded into the React Auth state.

---

## 6. Migration Guide

The migration is versioned via Alembic revision `6ab3db7907d9`:

```bash
# 1. Activate backend environment
cd backend
source venv/bin/activate

# 2. Upgrade schema to latest head
alembic upgrade head

# 3. Verify current revision
alembic current
# Output: 6ab3db7907d9 (head)
```

### Rollback Plan
If necessary to revert to the Module 1 baseline:
```bash
alembic downgrade a39ceb30351a
```
The downgrade drops the composite foreign keys, unique constraints, and `companies` table, restoring `tenants` without data loss.

---

## 7. Verification & Test Suite

The test suite contains 49 comprehensive tests, including 12 dedicated multi-company isolation tests:

```bash
cd backend
source venv/bin/activate
pytest -v tests/test_multi_company_isolation.py
```

### Verified Scenarios
1. ✅ `test_same_branch_code_allowed_in_different_companies`: Branches in different companies can share the same code (`CHENNAI`).
2. ✅ `test_duplicate_branch_code_within_same_company_rejected`: Duplicate branch codes in the same company trigger integrity violation.
3. ✅ `test_mismatched_company_and_branch_rejected_by_composite_fk`: PostgreSQL composite FK aborts inserting a document with `company_id=CompanyA` and `branch_id=CompanyB_Branch`.
4. ✅ `test_company_a_user_cannot_list_company_b_documents`: Zero leakage in document listing.
5. ✅ `test_company_b_user_cannot_list_company_a_documents`: Reciprocal tenant isolation.
6. ✅ `test_company_a_user_cannot_get_company_b_document_by_id`: Returns `404 Not Found`.
7. ✅ `test_company_a_user_cannot_download_company_b_file`: Media access returns `404 Not Found`.
8. ✅ `test_company_a_user_cannot_delete_company_b_document`: Deletion returns `404 Not Found`.
9. ✅ `test_company_a_user_cannot_reprocess_company_b_document`: Reprocessing returns `404 Not Found`.
10. ✅ `test_company_a_user_cannot_access_company_b_invoice`: Invoice isolation returns `404 Not Found`.
11. ✅ `test_tampered_company_id_in_payload_ignored`: Request payloads cannot forge or tamper with `company_id`.
12. ✅ `test_company_suspension_blocks_tenant_operations`: Suspended company users receive `403 Forbidden` across all endpoints.
