"""
Tests for app.config — environment safety, production validation, and settings helpers.
"""

import pytest
from app.config import Settings, validate_production_config


def test_settings_default_environment():
    settings = Settings()
    assert settings.APP_ENV in ("development", "test", "production")
    assert isinstance(settings.cors_origins_list, list)


def test_cors_origins_parsing():
    settings = Settings(CORS_ORIGINS="http://localhost:3000, https://myapp.com")
    assert settings.cors_origins_list == ["http://localhost:3000", "https://myapp.com"]

    wildcard_settings = Settings(CORS_ORIGINS="*")
    assert wildcard_settings.cors_origins_list == ["*"]


def test_production_validation_rejects_weak_secret():
    bad_cfg = Settings(
        APP_ENV="production",
        SECRET_KEY="super-secret-dms-jwt-key-change-in-production",
        GEMINI_API_KEY="valid-key",
        CORS_ORIGINS="https://app.example.com",
    )
    with pytest.raises(SystemExit):
        validate_production_config(bad_cfg)


def test_production_validation_rejects_wildcard_cors():
    bad_cfg = Settings(
        APP_ENV="production",
        SECRET_KEY="a" * 32,
        GEMINI_API_KEY="valid-key",
        CORS_ORIGINS="*",
    )
    with pytest.raises(SystemExit):
        validate_production_config(bad_cfg)


def test_production_validation_rejects_missing_gemini_key():
    bad_cfg = Settings(
        APP_ENV="production",
        SECRET_KEY="a" * 32,
        GEMINI_API_KEY=None,
        CORS_ORIGINS="https://app.example.com",
    )
    with pytest.raises(SystemExit):
        validate_production_config(bad_cfg)


def test_production_validation_passes_valid_config():
    valid_cfg = Settings(
        APP_ENV="production",
        SECRET_KEY="super-secure-production-jwt-key-with-sufficient-length",
        GEMINI_API_KEY="valid-gemini-key",
        CORS_ORIGINS="https://app.example.com",
        DATABASE_URL="postgresql://user:pass@dbserver:5432/dms_prod",
    )
    # Should not raise
    validate_production_config(valid_cfg)


def test_development_validation_does_not_abort_on_weak_secrets():
    dev_cfg = Settings(
        APP_ENV="development",
        SECRET_KEY="weak",
    )
    # In development, it logs a warning instead of SystemExit
    validate_production_config(dev_cfg)
