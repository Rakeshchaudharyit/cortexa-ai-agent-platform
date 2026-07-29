"""Typed application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "change_me",
        "change_me_to_a_long_random_string",
        "secret",
        "changeme",
    }
)


class Settings(BaseSettings):
    """Application configuration. Secrets are never logged by this module."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # Application
    app_name: str = Field(default="Cortexa AI Agent Platform", alias="APP_NAME")
    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        alias="APP_ENV",
    )
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Backend bind
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")

    # PostgreSQL
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="cortexa_agent", alias="POSTGRES_DB")
    postgres_user: str = Field(default="cortexa", alias="POSTGRES_USER")
    postgres_password: str = Field(default="local_development_only", alias="POSTGRES_PASSWORD")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    # Redis
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    # CORS — NoDecode keeps comma-separated env strings from being JSON-parsed first.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:13000",
            "http://127.0.0.1:13000",
        ],
        alias="CORS_ALLOWED_ORIGINS",
    )
    frontend_origin: str = Field(
        default="http://localhost:3000",
        alias="FRONTEND_ORIGIN",
    )

    # Authentication (Phase 3)
    jwt_secret_key: str = Field(
        default="dev-only-cortexa-jwt-secret-replace-before-production-use-32b",
        alias="JWT_SECRET_KEY",
        min_length=32,
    )
    jwt_algorithm: Literal["HS256"] = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_days: int = Field(
        default=14,
        ge=1,
        le=90,
        alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    auth_cookie_name: str = Field(default="cortexa_refresh", alias="AUTH_COOKIE_NAME")
    auth_cookie_secure: bool = Field(default=False, alias="AUTH_COOKIE_SECURE")
    auth_cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        alias="AUTH_COOKIE_SAMESITE",
    )
    auth_cookie_domain: str | None = Field(default=None, alias="AUTH_COOKIE_DOMAIN")
    auth_cookie_path: str = Field(default="/api/v1/auth", alias="AUTH_COOKIE_PATH")
    password_min_length: int = Field(default=12, ge=8, le=128, alias="PASSWORD_MIN_LENGTH")
    password_max_length: int = Field(default=128, ge=32, le=1024, alias="PASSWORD_MAX_LENGTH")

    # LLM provider (Phase 2 — Ollama)
    llm_provider: Literal["ollama"] = Field(default="ollama", alias="LLM_PROVIDER")
    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:7b", alias="OLLAMA_MODEL")
    ollama_request_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        le=600,
        alias="OLLAMA_REQUEST_TIMEOUT_SECONDS",
    )
    ollama_connect_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=120,
        alias="OLLAMA_CONNECT_TIMEOUT_SECONDS",
    )
    llm_max_input_characters: int = Field(
        default=32_000,
        ge=1,
        le=500_000,
        alias="LLM_MAX_INPUT_CHARACTERS",
    )
    llm_max_output_tokens: int = Field(
        default=2048,
        ge=1,
        le=8192,
        alias="LLM_MAX_OUTPUT_TOKENS",
    )
    llm_default_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        alias="LLM_DEFAULT_TEMPERATURE",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:13000",
                "http://127.0.0.1:13000",
            ]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        raise TypeError("CORS_ALLOWED_ORIGINS must be a string or list of strings")

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        prefix = value.strip()
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return prefix.rstrip("/") or "/api/v1"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return level

    @field_validator("llm_provider")
    @classmethod
    def normalize_llm_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider != "ollama":
            raise ValueError("LLM_PROVIDER must be 'ollama' in Phase 2")
        return provider

    @field_validator("ollama_base_url")
    @classmethod
    def normalize_ollama_base_url(cls, value: str) -> str:
        url = value.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must start with http:// or https://")
        return url

    @field_validator("ollama_model")
    @classmethod
    def normalize_ollama_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("OLLAMA_MODEL cannot be blank")
        return model

    @field_validator("jwt_secret_key")
    @classmethod
    def normalize_jwt_secret(cls, value: str) -> str:
        secret = value.strip()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return secret

    @field_validator("auth_cookie_samesite", mode="before")
    @classmethod
    def normalize_samesite(cls, value: object) -> str:
        if value is None or value == "":
            return "lax"
        return str(value).strip().lower()

    @field_validator("auth_cookie_domain", mode="before")
    @classmethod
    def normalize_cookie_domain(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("frontend_origin")
    @classmethod
    def normalize_frontend_origin(cls, value: str) -> str:
        origin = value.strip().rstrip("/")
        if not origin.startswith(("http://", "https://")):
            raise ValueError("FRONTEND_ORIGIN must start with http:// or https://")
        return origin

    @model_validator(mode="after")
    def build_connection_urls(self) -> Settings:
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
        if self.password_min_length > self.password_max_length:
            raise ValueError("PASSWORD_MIN_LENGTH cannot exceed PASSWORD_MAX_LENGTH")
        if self.is_production:
            lowered = self.jwt_secret_key.lower()
            if lowered in _INSECURE_JWT_SECRETS or "dev-only" in lowered or "replace" in lowered:
                raise ValueError(
                    "JWT_SECRET_KEY must be replaced with a strong secret in production"
                )
            if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true when SameSite=None")
        # Ensure frontend origin is always an allowed CORS origin.
        if self.frontend_origin not in self.cors_allowed_origins:
            self.cors_allowed_origins = [*self.cors_allowed_origins, self.frontend_origin]
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def safe_dict(self) -> dict[str, object]:
        """Return non-sensitive settings for diagnostics."""
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "app_debug": self.app_debug,
            "app_version": self.app_version,
            "api_prefix": self.api_prefix,
            "log_level": self.log_level,
            "backend_host": self.backend_host,
            "backend_port": self.backend_port,
            "cors_allowed_origins": self.cors_allowed_origins,
            "frontend_origin": self.frontend_origin,
            "jwt_algorithm": self.jwt_algorithm,
            "access_token_expire_minutes": self.access_token_expire_minutes,
            "refresh_token_expire_days": self.refresh_token_expire_days,
            "auth_cookie_name": self.auth_cookie_name,
            "auth_cookie_secure": self.auth_cookie_secure,
            "auth_cookie_samesite": self.auth_cookie_samesite,
            "auth_cookie_path": self.auth_cookie_path,
            "password_min_length": self.password_min_length,
            "password_max_length": self.password_max_length,
            "llm_provider": self.llm_provider,
            "ollama_model": self.ollama_model,
            "llm_max_input_characters": self.llm_max_input_characters,
            "llm_max_output_tokens": self.llm_max_output_tokens,
            "llm_default_temperature": self.llm_default_temperature,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings. Call clear_settings_cache() in tests."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache (for tests)."""
    get_settings.cache_clear()
