# Phase 1: Authentication and Frontend Audit Report

## 1. Audit Findings Summary

| Area | Current Implementation Status | Findings |
|---|---|---|
| **Access Token Storage** | CONFIRMED | Stored in `localStorage` (`dms_token`, `dms_user`). Must be transitioned to application memory + HttpOnly cookie for refresh tokens. |
| **JWT Generation & Expiry** | CONFIRMED | PyJWT `HS256`, 480 minutes expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`). Audience currently hardcoded to `dms-portal`. Needs portal-specific audiences (`platform`, `company`, `app`) and 15 min access expiry. |
| **JWT Verification** | CONFIRMED | `decode_token()` in `app/auth.py` validates signature, exp, and `dms-portal` audience. |
| **Refresh Tokens** | NOT IMPLEMENTED | Zero refresh token logic exists in backend or frontend. |
| **Logout & Invalidation** | NOT IMPLEMENTED | Frontend merely clears `localStorage`. Backend has no session table or token invalidation. |
| **User Status & Active Checks** | PARTIALLY IMPLEMENTED | `User` existence and company existence/suspension are checked in `AuthContext`, but `users` table lacks `status`, `token_version`, `failed_attempts`, `locked_until`, `must_change_password`. |
| **Company Suspension** | CONFIRMED | `CompanyStatus.SUSPENDED` is enforced on login and in `AuthContext.assert_active_company()`. |
| **Email / SMTP Service** | NOT IMPLEMENTED | No email sending capability exists in the backend. |
| **Rate Limiting** | NOT IMPLEMENTED | No request rate limiting or brute-force account lockout exists. |
| **Master Admin Identity** | NOT IMPLEMENTED | Only tenant `users` table exists. `GLOBAL_ADMIN` is scoped to its own company (`Vasanth & Co.`). Master Admin must be an independent table (`master_admins`). |
| **Portal Separation** | NOT IMPLEMENTED | Only `/login` exists. No `/admin/login` or `/company/login`. |
| **Invitations & Password Reset** | NOT IMPLEMENTED | No invitation or password recovery tables, endpoints, or UI exist. |

## 2. Answers to Specific Audit Questions

1. **Where is the access token currently stored?**
   - In browser `localStorage` as `dms_token`.
2. **How is the JWT generated?**
   - Via `create_access_token()` in `app/auth.py` with claims: `user_id`, `company_id`, `branch_id`, `tenant_id`, `role`, `exp`, `iat`, `aud`.
3. **How is the JWT verified?**
   - Via `decode_token()` in `app/auth.py` verifying `HS256` signature and `settings.JWT_AUDIENCE` (`dms-portal`).
4. **What is the current access token expiry?**
   - 480 minutes (8 hours) in `Settings.ACCESS_TOKEN_EXPIRE_MINUTES`.
5. **Is a refresh-token mechanism already present?**
   - No.
6. **Is logout implemented?**
   - Only client-side `localStorage.removeItem`. No backend session invalidation.
7. **Does logout actually invalidate the token?**
   - No. Tokens remain valid until their expiration timestamp.
8. **Does the backend check whether the user is active on every request?**
   - It verifies user row existence in the DB, but there is no `status` or `token_version` column.
9. **How is company suspension checked?**
   - Checked in `login()` route and `AuthContext.assert_active_company()`.
10. **Does an email-sending mechanism already exist?**
    - No.
11. **Is rate limiting already configured?**
    - No.
12. **How are existing users created?**
    - Seeded via `seed.py` (Jayasri, Samrethi, Sujipriya, Hindu Priya, Boomika).
13. **How are roles assigned?**
    - Directly via `UserRole` enum (`GLOBAL_ADMIN`, `ADMIN`, `STAFF`) stored in `users.role`.
14. **How are the three portal experiences currently represented in the frontend?**
    - There is only one single `/login` page and one `ProtectedRoute`.
15. **Are any existing endpoints dependent on the old JWT structure?**
    - Existing endpoints (`documents`, `invoices`, `auth/me`) depend on `AuthContext` which reads `user_id` from the decoded token. We must maintain backward compatibility for existing document and invoice endpoints while enforcing the new portal audiences.
