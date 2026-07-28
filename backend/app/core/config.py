"""Typed application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
        default_factory=lambda: ["http://localhost:3000"],
        alias="CORS_ALLOWED_ORIGINS",
    )

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
            return ["http://localhost:3000"]
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

    @model_validator(mode="after")
    def build_connection_urls(self) -> Settings:
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
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
