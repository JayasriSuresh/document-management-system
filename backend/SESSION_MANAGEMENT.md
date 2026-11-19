# 🔄 Session Management, Token Rotation & Replay Detection

## 1. Overview

Module 3 transitions DMS from stateless, non-revocable JWTs to **durable, rotated refresh-token sessions**.

- **Access Token Expiry:** 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Refresh Token Expiry:** 7 days (`REFRESH_TOKEN_EXPIRE_DAYS`).
- **Storage:** Refresh tokens are never stored in plaintext. Only SHA-256 digests are stored in `user_sessions`.
- **Transmission:** Delivered to browsers as `HttpOnly`, `Secure` (in prod), `SameSite=Lax` cookies.

---

## 2. Database Schema: `user_sessions`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `INTEGER` | Primary Key | Session identifier |
| `identity_type` | `VARCHAR(32)` | NOT NULL | `'master_admin'` or `'user'` |
| `user_id` | `INTEGER` | Nullable FK to `users.id` | Associated tenant user |
| `master_admin_id` | `INTEGER` | Nullable FK to `master_admins.id` | Associated Master Admin |
| `token_hash` | `VARCHAR(128)` | UNIQUE, NOT NULL, Indexed | SHA-256 digest of raw refresh token |
| `family_id` | `VARCHAR(64)` | NOT NULL, Indexed | Cryptographic session family UUID |
| `parent_session_id` | `INTEGER` | Nullable | Immediate ancestor session in rotation |
| `user_agent` | `VARCHAR(512)` | Nullable | Client user agent string |
| `ip_address` | `VARCHAR(64)` | Nullable | Client IP address |
| `expires_at` | `TIMESTAMP` | NOT NULL, Indexed | Session expiration boundary |
| `created_at` | `TIMESTAMP` | NOT NULL | Creation timestamp |
| `last_used_at` | `TIMESTAMP` | NOT NULL | Timestamp of last rotation |
| `revoked_at` | `TIMESTAMP` | Nullable | Revocation timestamp |
| `revoke_reason` | `VARCHAR(255)` | Nullable | `'rotated'`, `'logout'`, `'replay_attack_detected'`, etc. |

**Integrity Check Constraint:**
```sql
CONSTRAINT chk_user_session_identity CHECK (
    (identity_type = 'user' AND user_id IS NOT NULL AND master_admin_id IS NULL) OR
    (identity_type = 'master_admin' AND master_admin_id IS NOT NULL AND user_id IS NULL)
)
```

---

## 3. Refresh Token Rotation & Replay Detection

Every call to `POST /api/auth/refresh` rotates the refresh token:

```
[Client with Token A] ──POST /api/auth/refresh──> [Backend]
                                                      │
             ┌────────────────────────────────────────┴────────────────────────────────────────┐
             ▼                                                                                  ▼
     [Token A is Active]                                                              [Token A already Rotated]
             │                                                                                  │
  1. Revoke Token A (reason='rotated')                                              REPLAY ATTACK DETECTED!
  2. Issue Token B in same family_id                                                            │
  3. Set Cookie with Token B                                                        1. Revoke ALL sessions in family_id!
  4. Return new 15-min Access Token                                                 2. Return 401 Unauthorized
                                                                                    3. Clear client cookies
```

### Race-Condition Protection:
Database updates on `/api/auth/refresh` employ row-level locking (`with_for_update()`) ensuring simultaneous parallel requests cannot branch a single token into two active descendants.

---

## 4. Frontend Single-Flight Refresh Queue

Located in [frontend/src/api.js](file:///home/ubuntu/Downloads/Document_Management_System/frontend/src/api.js):
- When an access token expires, the first failing request sets `isRefreshing = true` and triggers `/api/auth/refresh`.
- Concurrent parallel requests are placed on a subscriber callback queue (`subscribeTokenRefresh`).
- Once refresh completes, all queued requests are replayed with the new access token.
- If refresh fails, authentication state is wiped and the user is redirected to the appropriate portal login.

---

## 5. Logout & Session Invalidation

1. **Standard Logout (`POST /api/auth/logout`):**
   - Marks the specific session record revoked (`revoke_reason='logout'`).
   - Clears the `dms_refresh_token` cookie.
2. **Logout All Sessions (`POST /api/auth/logout-all`):**
   - Marks all active sessions for that identity revoked (`revoke_reason='logout_all'`).
   - Increments `token_version` on the user or admin table.
   - Any currently active in-flight access tokens are rejected on their very next request due to `claim.token_version != user.token_version`.
