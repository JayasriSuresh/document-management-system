# ✉️ Invitations and Password Recovery Workflows

## 1. Corporate Workspace Invitations

Module 3 introduces an authorized, scoped invitation system enabling company administrators to invite new staff and managers securely.

### Database Schema: `invitations`

```sql
CREATE TABLE invitations (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    branch_id INTEGER NOT NULL,
    invited_role userrole NOT NULL,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    accepted_at TIMESTAMP WITHOUT TIME ZONE,
    revoked_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    CONSTRAINT fk_invitations_company_branch FOREIGN KEY (company_id, branch_id)
        REFERENCES branches(company_id, id) ON DELETE CASCADE
);
```

### Security Invariants:
1. **Role Escalation Protection:** Branch Admins cannot invite `GLOBAL_ADMIN` users (HTTP 403). Staff members cannot issue invitations (HTTP 403).
2. **Branch Scoping:** The selected branch must strictly belong to the inviter's company (`company_id`).
3. **Single-Use Tokens:** Tokens are 32-byte cryptographically random hex strings. The backend stores only their SHA-256 digest (`token_hash`).
4. **Atomic Acceptance:** `POST /api/auth/invite/accept` runs within a database transaction with row-level locks, ensuring a token can never be redeemed twice simultaneously.

---

## 2. Password Recovery (Anti-Enumeration)

### Database Schema: `password_resets`

```sql
CREATE TABLE password_resets (
    id SERIAL PRIMARY KEY,
    identity_type VARCHAR(32) NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    master_admin_id INTEGER REFERENCES master_admins(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    used_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    requested_ip VARCHAR(64),
    CONSTRAINT chk_password_reset_identity CHECK (
        (identity_type = 'user' AND user_id IS NOT NULL AND master_admin_id IS NULL) OR
        (identity_type = 'master_admin' AND master_admin_id IS NOT NULL AND user_id IS NULL)
    )
);
```

### Flow & Protections:
1. **Anti-Enumeration:**
   ```
   POST /api/auth/password/reset-request
   { "email": "any-input@example.com", "portal": "app" }
   ```
   Always responds with:
   `"If the account is eligible, password reset instructions will be sent."`
   Does not reveal if the email exists, is active, or is locked.
2. **Session Invalidation on Reset:**
   When a user redempts a reset token (`POST /api/auth/password/reset`):
   - The password hash is updated with bcrypt.
   - All active refresh sessions are revoked (`revoke_all_sessions`).
   - `token_version` is incremented.
   - Any currently active access tokens are immediately rejected.
3. **Forced Password Changes (`must_change_password`):**
   - If an account has `must_change_password=True`, the frontend redirects the user to `/change-password`.
   - Normal workspace access is blocked until the password is changed via `POST /api/auth/password/change`.
