# 📄 Document Management System (DMS)

A production-hardened Document & Invoice Management System built with **FastAPI**, **React**, **PostgreSQL**, **Tesseract OCR**, and **Google Gemini AI**.

---

## 🎯 Architecture & Capabilities

| Capability | Implementation | Status |
|---|---|---|
| **API Framework** | FastAPI (Lifespan, Pydantic v2 Settings) | ✅ |
| **Authentication** | PyJWT with portal-specific `aud` (platform, company, app) & bcrypt | ✅ |
| **Portals & Identity** | Three isolated portals (Platform, Company Admin, Branch Workspace) | ✅ |
| **Durable Sessions** | Rotated refresh-token cookies, replay detection, logout-all | ✅ |
| **Account Lifecycle** | Brute-force lockout (5 attempts), invitations, password recovery | ✅ |
| **Multi-Tenancy** | Company → Branch hierarchy, composite FKs, zero cross-tenant leakage | ✅ |
| **RBAC** | Global Admin, Branch Admin, Staff (30-day window) | ✅ |
| **Database Migrations**| Alembic with baseline, company hierarchy & identity migrations | ✅ |
| **Observability** | Request ID tracing (`X-Request-ID`) & structured logs | ✅ |
| **Error Handling** | Standardized JSON `{ error: { status, detail, request_id } }` | ✅ |
| **Test Suite** | Pytest (71 automated tests: auth, RBAC, docs, tenancy, portals) | ✅ |
| **CI Pipeline** | GitHub Actions (PostgreSQL service + migrations + pytest) | ✅ |
| **Document Processing**| Hybrid extraction: Local Regex/Fuzzy + Gemini Flash OCR | ✅ |
| **PDF Generation** | Jinja2 HTML templates + WeasyPrint rendering | ✅ |

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.12+ (or 3.13)
- Node.js 20+
- PostgreSQL 15+ running locally or in Docker
- Tesseract OCR & Poppler utilities

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng libpango-1.0-0 libharfbuzz0b poppler-utils
```

### 2. Start Services

```bash
chmod +x start.sh
./start.sh
```

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **Interactive Docs:** http://localhost:8000/docs (disabled in `APP_ENV=production`)

---

## 🧪 Testing & Quality Assurance

The backend includes a comprehensive pytest suite covering authentication, configuration guards, RBAC, document management, invoices, multi-company tenancy, portals, and durable sessions:

```bash
cd backend
source venv/bin/activate

# Run all 71 tests
pytest -v

# Run portal identity and session security test suite
pytest -v tests/test_module3_identity_and_portals.py

# Run with test coverage report
pytest --cov=app --cov-report=term-missing
```

### Technical Documentation:
- [AUTHENTICATION_ARCHITECTURE.md](backend/AUTHENTICATION_ARCHITECTURE.md): Multi-portal identity architecture & JWT security.
- [SESSION_MANAGEMENT.md](backend/SESSION_MANAGEMENT.md): Durable sessions, token rotation, and replay detection.
- [PORTAL_ACCESS_MATRIX.md](backend/PORTAL_ACCESS_MATRIX.md): Comprehensive portal and audience authorization matrix.
- [INVITATION_AND_PASSWORD_RESET.md](backend/INVITATION_AND_PASSWORD_RESET.md): Workspace invitation and password recovery workflows.
- [EMAIL_CONFIGURATION.md](backend/EMAIL_CONFIGURATION.md): SMTP configuration and development email simulator.
- [COMPANY_TENANCY.md](backend/COMPANY_TENANCY.md): Company → Branch hierarchy and composite foreign keys.
- [MIGRATIONS.md](backend/MIGRATIONS.md): Database migration workflows and revision history.

---

## 🗄️ Database Migrations

Database schema is managed using **Alembic**:

```bash
cd backend
source venv/bin/activate

# Apply migrations
alembic upgrade head

# Check status
alembic current
```

See [MIGRATIONS.md](backend/MIGRATIONS.md) for full migration workflows.

---

## ⚙️ Environment Variables

Configure these in `backend/.env` or in your deployment environment:

| Variable | Default / Example | Purpose |
|---|---|---|
| `APP_ENV` | `development` (`production`, `test`) | Environment mode; triggers strict startup validation in `production` |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection string |
| `SECRET_KEY` | *(Must be 32+ chars in prod)* | Secret key used for signing JWT tokens |
| `ALGORITHM` | `HS256` | JWT signature algorithm |
| `JWT_AUDIENCE` | `dms-portal` | Expected token audience claim |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | JWT expiration duration in minutes |
| `CORS_ORIGINS` | `*` (development only) | Comma-separated list of allowed frontend origins in production |
| `STORAGE_PATH` | `./storage/documents` | Directory for uploaded documents and generated PDFs |
| `GEMINI_API_KEY` | *(Secret API key)* | Google Gemini Flash API key for document extraction |
| `SEED_ALLOW_IN_PRODUCTION` | `0` | Guard preventing accidental demo seed data in production |
| `SEED_ADMIN_EMAIL` | *(Optional)* | Admin email for initial production bootstrap |
| `SEED_ADMIN_PASSWORD` | *(Optional)* | Admin password for initial production bootstrap |

---

## 🔒 Security Hardening

1. **PyJWT Migration**: Replaced deprecated `python-jose` with `PyJWT`. Tokens carry validated audience (`aud`), issued-at (`iat`), and expiration (`exp`) timestamps.
2. **Production Startup Validator**: When `APP_ENV=production`, the application refuses to start if `SECRET_KEY` is weak/default, if `CORS_ORIGINS` contains `*`, or if `GEMINI_API_KEY` is missing.
3. **Seeding Guard**: In production, default mock accounts (`Pasword@123`) and table wipes are blocked by default.
4. **Standardized Error Responses**: All API errors follow a predictable JSON format without leaking internal stack traces or database connection details.
5. **Request Tracing**: `X-Request-ID` is assigned to each incoming request, injected into logging contexts, and returned in response headers for end-to-end debugging.
