"""Configuration parsing tests."""

from __future__ import annotations

import pytest
from app.core.config import Settings, clear_settings_cache, get_settings
from pydantic import ValidationError


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    for key in list(Settings.model_fields.keys()):
        monkeypatch.delenv(key.upper(), raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    settings = Settings()
    assert settings.app_name == "Cortexa AI Agent Platform"
    assert settings.app_env == "development"
    assert settings.app_version == "0.1.0"
    assert settings.api_prefix == "/api/v1"
    assert settings.postgres_db == "cortexa_agent"
    assert settings.database_url is not None
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.cors_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:13000",
        "http://127.0.0.1:13000",
    ]
    clear_settings_cache()


def test_cors_origins_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000, http://127.0.0.1:3000",
    )
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    settings = Settings()
    assert settings.cors_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_api_prefix_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PREFIX", "api/v1/")
    settings = Settings()
    assert settings.api_prefix == "/api/v1"


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    clear_settings_cache()
    first = get_settings()
    second = get_settings()
    assert first is second
    clear_settings_cache()


def test_safe_dict_omits_secrets() -> None:
    settings = Settings(
        postgres_password="super-secret",
        database_url="postgresql+asyncpg://u:super-secret@db:5432/db",
        redis_url="redis://:secret@redis:6379/0",
        jwt_secret_key="test-only-cortexa-jwt-secret-key-32chars-min",
    )
    safe = settings.safe_dict()
    serialized = str(safe)
    assert "super-secret" not in serialized
    assert "postgres_password" not in safe
    assert "database_url" not in safe
    assert "redis_url" not in safe
    assert "jwt_secret_key" not in safe
    assert "super-secret" not in serialized
    assert ":secret@" not in serialized


def test_production_rejects_insecure_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "dev-only-cortexa-jwt-secret-replace-before-production-use-32b",
    )
    with pytest.raises(ValidationError):
        Settings()
