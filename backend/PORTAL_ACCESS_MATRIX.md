# 🛡️ Portal Access & Security Matrix

## 1. Identity & Portal Eligibility Matrix

| Identity Role | Platform Portal (`/admin/login`) | Company Portal (`/company/login`) | App Portal (`/login`) |
|---|---|---|---|
| **Master Admin** (`master_admins`) | ✅ **ALLOWED** (`aud="platform"`) | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 401) |
| **Global Admin** (`GLOBAL_ADMIN`) | ❌ **REJECTED** (HTTP 401) | ✅ **ALLOWED** (`aud="company"`) | ❌ **REJECTED** (HTTP 403 Forbidden) |
| **Branch Admin** (`ADMIN`) | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 403 Forbidden) | ✅ **ALLOWED** (`aud="app"`) |
| **Branch Staff** (`STAFF`) | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 403 Forbidden) | ✅ **ALLOWED** (`aud="app"`) |

---

## 2. Token Audience Validation Matrix

| Token Claim (`aud`) | Platform Endpoints (`require_platform`) | Company Endpoints (`require_company`) | App Endpoints (`require_app`) | Document/Invoice APIs (`get_auth_context`) |
|---|---|---|---|---|
| `aud="platform"` | ✅ **ALLOWED** | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (Tenant identity required) |
| `aud="company"` | ❌ **REJECTED** (HTTP 401) | ✅ **ALLOWED** | ❌ **REJECTED** (HTTP 403) | ✅ **ALLOWED** (Company tenant scope) |
| `aud="app"` | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 403) | ✅ **ALLOWED** | ✅ **ALLOWED** (Branch tenant scope) |
| Missing / Tampered | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 401) | ❌ **REJECTED** (HTTP 401) |

---

## 3. Account Status & Lifecycle Matrix

| Account Status | Login Allowed | Token Refresh Allowed | Active Access Token Valid |
|---|---|---|---|
| **`ACTIVE`** | ✅ Yes | ✅ Yes | ✅ Yes |
| **`INACTIVE`** | ❌ No (HTTP 403) | ❌ No (HTTP 403) | ❌ No (HTTP 403) |
| **`LOCKED`** | ❌ No (HTTP 423) | ❌ No (HTTP 403) | ❌ No (HTTP 403) |

---

## 4. Company Tenancy Lifecycle Matrix

| Company Status | Global Admin (Company Portal) | Branch Admin (App Portal) | Branch Staff (App Portal) | Document / Invoice Access |
|---|---|---|---|---|
| **`ACTIVE`** | ✅ Allowed | ✅ Allowed | ✅ Allowed | ✅ Allowed |
| **`SUSPENDED`** | ⚠️ Allowed (Inspection only) | ❌ Blocked (HTTP 403) | ❌ Blocked (HTTP 403) | ❌ Blocked (HTTP 403) |
