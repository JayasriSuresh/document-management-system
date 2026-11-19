"""
Application configuration — single source of truth.

All settings are read from environment variables (or .env) via Pydantic Settings.
Production startup validation is enforced in app/main.py via validate_production_config().
"""

import sys
import secrets
from typing import Literal, Optional

from pydantic_settings import BaseSettings


_KNOWN_WEAK_SECRETS = {
    "super-secret-dms-jwt-key-change-in-production",
    "secret",
    "changeme",
    "your-secret-key",
}


class Settings(BaseSettings):
    # ── Core ─────────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://dms_user:dms_password@localhost:5433/dms_db"
    SECRET_KEY: str = "super-secret-dms-jwt-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    STORAGE_PATH: str = "./storage/documents"
    GEMINI_API_KEY: Optional[str] = None

    # ── Environment mode ─────────────────────────────────────────────────────
    # Set APP_ENV=production in your deployment environment.
    APP_ENV: Literal["development", "production", "test"] = "development"

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated allowed origins. In production, set this explicitly.
    CORS_ORIGINS: str = "*"

    # ── Token audiences & Portals ─────────────────────────────────────────────
    JWT_AUDIENCE: str = "dms-portal"  # legacy compatibility
    JWT_AUDIENCE_PLATFORM: str = "platform"
    JWT_AUDIENCE_COMPANY: str = "company"
    JWT_AUDIENCE_APP: str = "app"

    # ── Security & Lockout ───────────────────────────────────────────────────
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    # ── Multi-Factor Authentication (MFA) ────────────────────────────────────
    MFA_ENCRYPTION_KEY: Optional[str] = None
    MFA_ISSUER_NAME: str = "DMS"
    MFA_PENDING_TOKEN_EXPIRE_MINUTES: int = 5
    MFA_MAX_FAILED_ATTEMPTS: int = 5
    MFA_LOCKOUT_MINUTES: int = 15

    # ── Invitations & Password Reset ─────────────────────────────────────────
    INVITATION_EXPIRE_HOURS: int = 48
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60

    # ── Email / SMTP ─────────────────────────────────────────────────────────
    SMTP_HOST: Optional[str] = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_PASS: Optional[str] = None
    SMTP_FROM_EMAIL: str = "jayasriinkwc@gmail.com"
    SMTP_FROM_NAME: str = "DMS Platform Administration"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Cookies ──────────────────────────────────────────────────────────────
    COOKIE_SECURE: bool = False  # set True automatically in production if not explicitly overridden
    COOKIE_SAMESITE: str = "lax"

    # ── Module 9: Pipeline Hardening, Limits & Queue ─────────────────────────
    MAX_UPLOAD_FILE_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB
    MAX_BATCH_FILES: int = 10
    MAX_TOTAL_BATCH_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    MAX_PDF_PAGES: int = 50
    MAX_IMAGE_WIDTH: int = 10000
    MAX_IMAGE_HEIGHT: int = 10000
    MAX_IMAGE_PIXELS: int = 40000000  # 40 MP
    QUEUE_LOCK_TIMEOUT_SECONDS: int = 300  # 5 minutes
    QUEUE_MAX_ATTEMPTS: int = 3
    QUEUE_POLL_INTERVAL_SECONDS: float = 1.0

    class Config:
        env_file = ".env"
        extra = "ignore"

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_test(self) -> bool:
        return self.APP_ENV == "test"

    @property
    def is_cookie_secure(self) -> bool:
        if self.COOKIE_SECURE:
            return True
        return self.is_production

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS as a list. '*' is returned as-is for wildcard."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


def validate_production_config(cfg: "Settings") -> None:
    """
    Hard-fail startup checks that MUST pass before the app serves traffic in
    production. Call this once from main.py lifespan / startup event.

    In development the checks are logged as warnings but do not block startup.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Weak SECRET_KEY
    if cfg.SECRET_KEY in _KNOWN_WEAK_SECRETS or len(cfg.SECRET_KEY) < 32:
        msg = (
            "SECRET_KEY is weak or default. "
            f"Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        if cfg.is_production:
            errors.append(msg)
        else:
            warnings.append(msg)

    # 2. GEMINI_API_KEY in production
    if cfg.is_production and not cfg.GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY must be set in production.")

    # 3. Wildcard CORS in production
    if cfg.is_production and cfg.CORS_ORIGINS.strip() == "*":
        errors.append(
            "CORS_ORIGINS='*' is not allowed in production. "
            "Set it to your frontend domain (e.g. https://app.example.com)."
        )

    # 4. Warn about SQLite in production (unlikely but guard anyway)
    if cfg.is_production and cfg.DATABASE_URL.startswith("sqlite"):
        errors.append("SQLite is not supported in production. Use PostgreSQL.")

    # ── Report ────────────────────────────────────────────────────────────────
    import logging
    logger = logging.getLogger("dms.config")

    for w in warnings:
        logger.warning("CONFIG WARNING: %s", w)

    if errors:
        for e in errors:
            logger.critical("CONFIG ERROR: %s", e)
        sys.exit(
            "\n❌ Production configuration errors detected. "
            "Fix the above CONFIG ERROR entries and restart.\n"
            + "\n".join(f"  • {e}" for e in errors)
        )


settings = Settings()
