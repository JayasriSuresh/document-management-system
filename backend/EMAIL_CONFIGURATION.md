# 📧 Email Delivery Service Configuration

## 1. Overview

The DMS Identity service handles email dispatch for:
- Corporate workspace invitations (`/accept-invite?token=...`)
- Password recovery links (`/reset-password?token=...`)

---

## 2. Environment Variables

Configure these settings in `backend/.env` or in container environment variables:

| Variable | Default / Example | Purpose |
|---|---|---|
| `SMTP_HOST` | `smtp.example.com` | SMTP relay server hostname (if omitted in dev, logs to console) |
| `SMTP_PORT` | `587` | SMTP port (typically `587` for STARTTLS, `465` for SSL) |
| `SMTP_USERNAME` | `postmaster@example.com` | SMTP authentication user |
| `SMTP_PASSWORD` | `secret-smtp-password` | SMTP authentication password |
| `SMTP_FROM_EMAIL`| `security@dms.local` | Sender email address on outgoing messages |
| `SMTP_FROM_NAME` | `DMS Identity Security` | Display name of outgoing emails |
| `SMTP_USE_TLS`  | `True` | Negotiate STARTTLS on port 587 |
| `SMTP_USE_SSL`  | `False` | Connect via direct SSL socket on port 465 |
| `FRONTEND_URL`  | `http://localhost:5173` | Base URL used to build invite and reset links |

---

## 3. Operational Behavior

### Development Mode (`APP_ENV=development`):
If `SMTP_HOST` is not configured, the service falls back to the **Dev Email Simulator**, logging links directly to the terminal stdout:
```
==================== [DEV EMAIL SIMULATOR] ====================
To: engineer@example.com
Subject: Invitation to join Vasanth & Co. on DMS

Hello,
You have been invited to join Vasanth & Co. (Chennai branch) as a STAFF.
To complete registration, visit:
http://localhost:5173/accept-invite?token=8c6...
================================================================
```

### Production Mode (`APP_ENV=production`):
- `SMTP_HOST` is required for email-dependent endpoints.
- If SMTP connection or authentication fails, an exception is raised so the API reports delivery failure instead of falsely confirming delivery.
- Sensitive tokens are **never** logged to production log files.
