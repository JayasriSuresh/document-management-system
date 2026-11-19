# 🔐 Authentication & Identity Architecture (Module 3)

## 1. Overview & Identity Model

Module 3 introduces a secure, unified multi-portal identity architecture across the Document Management System (DMS).

### Three Distinct Identity Types & Portals

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Master Platform Portal                          │
│   • Route: /admin/login                                                │
│   • Identity Table: master_admins                                      │
│   • Token Audience: aud="platform"                                     │
│   • Role: MASTER_ADMIN                                                 │
│   • Scope: Global system infrastructure, hardware & tenant management  │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                        Company Admin Portal                            │
│   • Route: /company/login                                              │
│   • Identity Table: users (role = GLOBAL_ADMIN)                        │
│   • Token Audience: aud="company"                                      │
│   • Scope: Corporate headquarters, company-wide settings & branches    │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                       Branch Workspace Portal                          │
│   • Route: /login                                                      │
│   • Identity Table: users (role in ADMIN, STAFF)                       │
│   • Token Audience: aud="app"                                          │
│   • Scope: Branch-level document operations, uploads, invoices        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Centralized Authentication Service

Rather than fragmenting authentication across multiple endpoints or services, all logins converge into a single hardened backend service:

```
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "user-password",
  "portal": "platform" | "company" | "app"
}
```

### Authentication Execution Flow:
1. **Portal Parameter Validation:** The backend validates that `portal` matches one of the three supported portals.
2. **Identity Resolution:**
   - `portal="platform"` resolves strictly against `master_admins`. Normal tenant users are rejected.
   - `portal="company"` resolves against `users` and strictly demands `role == UserRole.GLOBAL_ADMIN`.
   - `portal="app"` resolves against `users` and strictly demands `role in (UserRole.ADMIN, UserRole.STAFF)`.
3. **Lockout Check:** Evaluates `locked_until` timestamp. If account is locked due to consecutive failures, returns `HTTP 423 Locked`.
4. **Password Verification:** Cryptographically validates password via bcrypt `checkpw`. On failure, increments `failed_attempts` and triggers lockout if threshold (5) is reached.
5. **Account Status Evaluation:** Checks `status == AccountStatus.ACTIVE`. Inactive or suspended accounts receive `HTTP 403 Forbidden`.
6. **Company Tenancy Validation:** For tenant users, validates `Company.status == CompanyStatus.ACTIVE`. Suspended company users are blocked immediately.
7. **Durable Session Creation:** Generates a 32-byte cryptographic refresh token, stores its SHA-256 hash in `user_sessions`, and sets it as a secure, `HttpOnly`, `SameSite=Lax` cookie.
8. **Short-Lived JWT Issuance:** Generates an access token with explicit audience matching the portal (`aud="platform"`, `aud="company"`, or `aud="app"`).

---

## 3. JWT Audience Security

Access tokens are short-lived (15 minutes) and signed with `HS256` using the centralized `SECRET_KEY`.

### Token Payload Structure:
```json
{
  "sub": "user@example.com",
  "uid": 12,
  "user_id": 12,
  "company_id": 2,
  "branch_id": 1,
  "role": "GLOBAL_ADMIN",
  "identity_type": "user",
  "token_version": 1,
  "aud": "company",
  "jti": "d3b07384d113edec49eaa6238ad5ff00",
  "iat": 1793444000,
  "exp": 1793444900
}
```

### Backend Enforcement:
Endpoints use FastAPI dependencies that strictly enforce audience claims:
- `require_portal("platform")`: Demands `aud="platform"` and `MasterAdmin` identity.
- `require_portal("company")`: Demands `aud="company"` and `UserRole.GLOBAL_ADMIN`.
- `require_portal("app")`: Demands `aud="app"` and `UserRole.ADMIN` or `STAFF`.
- `get_auth_context`: Permits both `"company"` and `"app"` tokens for tenant document/invoice operations.

**Cross-Portal Guarantee:** A valid token issued for the App Portal (`aud="app"`) is rejected with `401 Unauthorized` / `403 Forbidden` if presented to the Company Admin or Platform Portal.
