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
    expected_application_id: str = Field(
        default="cortexa-ai-agent-platform",
        alias="EXPECTED_APPLICATION_ID",
    )
    expected_database_identity: str = Field(
        default="cortexa-agent-development",
        alias="EXPECTED_DATABASE_IDENTITY",
    )
    database_identity_check_enabled: bool = Field(
        default=True,
        alias="DATABASE_IDENTITY_CHECK_ENABLED",
    )
    legacy_db_migration_allow_production: bool = Field(
        default=False,
        alias="LEGACY_DB_MIGRATION_ALLOW_PRODUCTION",
    )
    admin_user_cli_allow_production: bool = Field(
        default=False,
        alias="ADMIN_USER_CLI_ALLOW_PRODUCTION",
    )
    password_reset_dev_notice_enabled: bool = Field(
        default=True,
        alias="PASSWORD_RESET_DEV_NOTICE_ENABLED",
    )

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

    # Password reset (Phase 5.1)
    password_reset_enabled: bool = Field(default=True, alias="PASSWORD_RESET_ENABLED")
    password_reset_token_expire_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        alias="PASSWORD_RESET_TOKEN_EXPIRE_MINUTES",
    )
    password_reset_token_bytes: int = Field(
        default=32,
        ge=16,
        le=64,
        alias="PASSWORD_RESET_TOKEN_BYTES",
    )
    password_reset_max_active_tokens: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="PASSWORD_RESET_MAX_ACTIVE_TOKENS",
    )
    password_reset_request_cooldown_seconds: int = Field(
        default=60,
        ge=0,
        le=3600,
        alias="PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS",
    )
    password_reset_frontend_url: str = Field(
        default="http://localhost:13000/reset-password",
        alias="PASSWORD_RESET_FRONTEND_URL",
    )
    password_reset_delivery_provider: Literal["development"] = Field(
        default="development",
        alias="PASSWORD_RESET_DELIVERY_PROVIDER",
    )
    password_reset_dev_expose_token: bool = Field(
        default=False,
        alias="PASSWORD_RESET_DEV_EXPOSE_TOKEN",
    )
    password_reset_ip_hash_secret: str | None = Field(
        default=None,
        alias="PASSWORD_RESET_IP_HASH_SECRET",
    )
    password_reset_user_agent_hash_secret: str | None = Field(
        default=None,
        alias="PASSWORD_RESET_USER_AGENT_HASH_SECRET",
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
    ollama_keep_alive: str = Field(default="10m", alias="OLLAMA_KEEP_ALIVE")
    ollama_chat_num_predict: int | None = Field(
        default=None,
        ge=1,
        le=8192,
        alias="OLLAMA_CHAT_NUM_PREDICT",
    )
    ollama_chat_num_ctx: int | None = Field(
        default=None,
        ge=512,
        le=131_072,
        alias="OLLAMA_CHAT_NUM_CTX",
    )
    ollama_first_token_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=600,
        alias="OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS",
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

    # Documents / storage (Phase 4)
    document_upload_enabled: bool = Field(default=True, alias="DOCUMENT_UPLOAD_ENABLED")
    document_storage_path: str = Field(
        default="/tmp/cortexa-documents",
        alias="DOCUMENT_STORAGE_PATH",
    )
    document_max_file_size_bytes: int = Field(
        default=5_242_880,  # 5 MiB
        ge=1_024,
        le=52_428_800,
        alias="DOCUMENT_MAX_FILE_SIZE_BYTES",
    )
    document_allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [".txt", ".md", ".pdf", ".docx"],
        alias="DOCUMENT_ALLOWED_EXTENSIONS",
    )
    document_max_text_characters: int = Field(
        default=500_000,
        ge=1_000,
        le=5_000_000,
        alias="DOCUMENT_MAX_TEXT_CHARACTERS",
    )
    document_max_chunks: int = Field(
        default=500,
        ge=1,
        le=5_000,
        alias="DOCUMENT_MAX_CHUNKS",
    )

    # Chunking (Phase 4)
    chunk_size_characters: int = Field(
        default=1_200,
        ge=100,
        le=20_000,
        alias="CHUNK_SIZE_CHARACTERS",
    )
    chunk_overlap_characters: int = Field(
        default=200,
        ge=0,
        le=5_000,
        alias="CHUNK_OVERLAP_CHARACTERS",
    )
    chunk_min_characters: int = Field(
        default=40,
        ge=1,
        le=5_000,
        alias="CHUNK_MIN_CHARACTERS",
    )

    # Embeddings (Phase 4)
    embedding_provider: Literal["ollama"] = Field(
        default="ollama",
        alias="EMBEDDING_PROVIDER",
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",
        alias="OLLAMA_EMBEDDING_MODEL",
    )
    embedding_dimension: int = Field(
        default=768,
        ge=8,
        le=4096,
        alias="EMBEDDING_DIMENSION",
    )
    embedding_batch_size: int = Field(
        default=16,
        ge=1,
        le=128,
        alias="EMBEDDING_BATCH_SIZE",
    )
    embedding_request_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=600,
        alias="EMBEDDING_REQUEST_TIMEOUT_SECONDS",
    )
    embedding_max_input_characters: int = Field(
        default=8_000,
        ge=100,
        le=100_000,
        alias="EMBEDDING_MAX_INPUT_CHARACTERS",
    )

    # RAG retrieval / generation (Phase 4)
    rag_default_top_k: int = Field(default=5, ge=1, le=50, alias="RAG_DEFAULT_TOP_K")
    rag_max_top_k: int = Field(default=20, ge=1, le=100, alias="RAG_MAX_TOP_K")
    rag_min_similarity: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        alias="RAG_MIN_SIMILARITY",
    )
    rag_max_query_characters: int = Field(
        default=2_000,
        ge=1,
        le=20_000,
        alias="RAG_MAX_QUERY_CHARACTERS",
    )
    rag_max_context_characters: int = Field(
        default=12_000,
        ge=500,
        le=200_000,
        alias="RAG_MAX_CONTEXT_CHARACTERS",
    )
    rag_citation_excerpt_characters: int = Field(
        default=280,
        ge=40,
        le=2_000,
        alias="RAG_CITATION_EXCERPT_CHARACTERS",
    )

    # Conversations / multi-turn chat (Phase 5)
    conversation_max_history_messages: int = Field(
        default=20,
        ge=2,
        le=200,
        alias="CONVERSATION_MAX_HISTORY_MESSAGES",
    )
    conversation_max_history_characters: int = Field(
        default=16_000,
        ge=500,
        le=500_000,
        alias="CONVERSATION_MAX_HISTORY_CHARACTERS",
    )
    conversation_max_context_characters: int = Field(
        default=24_000,
        ge=1_000,
        le=500_000,
        alias="CONVERSATION_MAX_CONTEXT_CHARACTERS",
    )
    conversation_summary_trigger_messages: int = Field(
        default=12,
        ge=4,
        le=500,
        alias="CONVERSATION_SUMMARY_TRIGGER_MESSAGES",
    )
    conversation_summary_max_characters: int = Field(
        default=1_500,
        ge=100,
        le=20_000,
        alias="CONVERSATION_SUMMARY_MAX_CHARACTERS",
    )
    conversation_title_max_characters: int = Field(
        default=80,
        ge=8,
        le=200,
        alias="CONVERSATION_TITLE_MAX_CHARACTERS",
    )
    message_max_characters: int = Field(
        default=8_000,
        ge=100,
        le=100_000,
        alias="MESSAGE_MAX_CHARACTERS",
    )
    message_max_response_tokens: int = Field(
        default=2_048,
        ge=64,
        le=8_192,
        alias="MESSAGE_MAX_RESPONSE_TOKENS",
    )
    chat_default_temperature: float = Field(
        default=0.4,
        ge=0.0,
        le=2.0,
        alias="CHAT_DEFAULT_TEMPERATURE",
    )
    chat_default_top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        alias="CHAT_DEFAULT_TOP_K",
    )
    conversation_search_max_results: int = Field(
        default=25,
        ge=1,
        le=100,
        alias="CONVERSATION_SEARCH_MAX_RESULTS",
    )
    conversation_list_default_limit: int = Field(
        default=20,
        ge=1,
        le=100,
        alias="CONVERSATION_LIST_DEFAULT_LIMIT",
    )
    conversation_list_max_limit: int = Field(
        default=50,
        ge=1,
        le=200,
        alias="CONVERSATION_LIST_MAX_LIMIT",
    )
    citation_excerpt_max_characters: int = Field(
        default=280,
        ge=40,
        le=2_000,
        alias="CITATION_EXCERPT_MAX_CHARACTERS",
    )
    conversation_auto_title_enabled: bool = Field(
        default=True,
        alias="CONVERSATION_AUTO_TITLE_ENABLED",
    )
    conversation_summary_enabled: bool = Field(
        default=True,
        alias="CONVERSATION_SUMMARY_ENABLED",
    )
    chat_general_mode_enabled: bool = Field(
        default=True,
        alias="CHAT_GENERAL_MODE_ENABLED",
    )

    # Agent tools (Phase 6)
    agent_tools_enabled: bool = Field(default=True, alias="AGENT_TOOLS_ENABLED")
    agent_max_tool_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="AGENT_MAX_TOOL_ITERATIONS",
    )
    agent_tool_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        alias="AGENT_TOOL_TIMEOUT_SECONDS",
    )
    agent_max_result_bytes: int = Field(
        default=32_768,
        ge=1024,
        le=1_048_576,
        alias="AGENT_MAX_RESULT_BYTES",
    )

    # Long-term memory (Phase 7)
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    memory_automatic_extraction_default: bool = Field(
        default=False,
        alias="MEMORY_AUTOMATIC_EXTRACTION_DEFAULT",
    )
    memory_suggestions_default: bool = Field(
        default=True,
        alias="MEMORY_SUGGESTIONS_DEFAULT",
    )
    memory_require_confirmation_default: bool = Field(
        default=True,
        alias="MEMORY_REQUIRE_CONFIRMATION_DEFAULT",
    )
    memory_max_active_per_user: int = Field(
        default=100,
        ge=1,
        le=500,
        alias="MEMORY_MAX_ACTIVE_PER_USER",
    )
    memory_max_retrieval_results: int = Field(
        default=5,
        ge=1,
        le=20,
        alias="MEMORY_MAX_RETRIEVAL_RESULTS",
    )
    memory_max_content_characters: int = Field(
        default=2_000,
        ge=40,
        le=10_000,
        alias="MEMORY_MAX_CONTENT_CHARACTERS",
    )
    memory_title_max_characters: int = Field(
        default=200,
        ge=8,
        le=200,
        alias="MEMORY_TITLE_MAX_CHARACTERS",
    )
    memory_context_max_characters: int = Field(
        default=3_000,
        ge=200,
        le=20_000,
        alias="MEMORY_CONTEXT_MAX_CHARACTERS",
    )
    memory_default_expiration_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        alias="MEMORY_DEFAULT_EXPIRATION_DAYS",
    )
    memory_min_relevance_score: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        alias="MEMORY_MIN_RELEVANCE_SCORE",
    )
    memory_duplicate_similarity_threshold: float = Field(
        default=0.92,
        ge=0.5,
        le=1.0,
        alias="MEMORY_DUPLICATE_SIMILARITY_THRESHOLD",
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

    @field_validator("document_allowed_extensions", mode="before")
    @classmethod
    def parse_document_extensions(cls, value: object) -> list[str]:
        if value is None or value == "":
            return [".txt", ".md", ".pdf", ".docx"]
        if isinstance(value, list):
            items = value
        elif isinstance(value, str):
            items = value.split(",")
        else:
            raise TypeError("DOCUMENT_ALLOWED_EXTENSIONS must be a string or list")
        normalized: list[str] = []
        for item in items:
            ext = str(item).strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.append(ext)
        return normalized or [".txt", ".md", ".pdf", ".docx"]

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

    @field_validator("embedding_provider")
    @classmethod
    def normalize_embedding_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider != "ollama":
            raise ValueError("EMBEDDING_PROVIDER must be 'ollama' in Phase 4")
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

    @field_validator("ollama_embedding_model")
    @classmethod
    def normalize_ollama_embedding_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("OLLAMA_EMBEDDING_MODEL cannot be blank")
        return model

    @field_validator("document_storage_path")
    @classmethod
    def normalize_document_storage_path(cls, value: str) -> str:
        path = value.strip()
        if not path:
            raise ValueError("DOCUMENT_STORAGE_PATH cannot be blank")
        if "\x00" in path:
            raise ValueError("DOCUMENT_STORAGE_PATH cannot contain null bytes")
        return path

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

    @field_validator("password_reset_frontend_url")
    @classmethod
    def normalize_password_reset_frontend_url(cls, value: str) -> str:
        url = value.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("PASSWORD_RESET_FRONTEND_URL must start with http:// or https://")
        return url.rstrip("?")

    @field_validator("password_reset_delivery_provider", mode="before")
    @classmethod
    def normalize_password_reset_delivery_provider(cls, value: object) -> str:
        if value is None or value == "":
            return "development"
        provider = str(value).strip().lower()
        if provider != "development":
            raise ValueError("PASSWORD_RESET_DELIVERY_PROVIDER must be 'development' in Phase 5.1")
        return provider

    @field_validator(
        "password_reset_ip_hash_secret",
        "password_reset_user_agent_hash_secret",
        mode="before",
    )
    @classmethod
    def normalize_optional_reset_secrets(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("memory_default_expiration_days", mode="before")
    @classmethod
    def normalize_memory_expiration_days(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError("MEMORY_DEFAULT_EXPIRATION_DAYS must be an integer or empty")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value.strip())
        raise ValueError("MEMORY_DEFAULT_EXPIRATION_DAYS must be an integer or empty")

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
        if self.chunk_overlap_characters >= self.chunk_size_characters:
            raise ValueError("CHUNK_OVERLAP_CHARACTERS must be less than CHUNK_SIZE_CHARACTERS")
        if self.rag_default_top_k > self.rag_max_top_k:
            raise ValueError("RAG_DEFAULT_TOP_K cannot exceed RAG_MAX_TOP_K")
        if self.conversation_list_default_limit > self.conversation_list_max_limit:
            raise ValueError(
                "CONVERSATION_LIST_DEFAULT_LIMIT cannot exceed CONVERSATION_LIST_MAX_LIMIT"
            )
        if self.chat_default_top_k > self.rag_max_top_k:
            raise ValueError("CHAT_DEFAULT_TOP_K cannot exceed RAG_MAX_TOP_K")
        if self.message_max_response_tokens > self.llm_max_output_tokens:
            raise ValueError("MESSAGE_MAX_RESPONSE_TOKENS cannot exceed LLM_MAX_OUTPUT_TOKENS")
        if self.embedding_dimension != 768 and self.ollama_embedding_model == "nomic-embed-text":
            raise ValueError(
                "EMBEDDING_DIMENSION must be 768 when OLLAMA_EMBEDDING_MODEL is nomic-embed-text"
            )
        if self.is_production:
            lowered = self.jwt_secret_key.lower()
            if lowered in _INSECURE_JWT_SECRETS or "dev-only" in lowered or "replace" in lowered:
                raise ValueError(
                    "JWT_SECRET_KEY must be replaced with a strong secret in production"
                )
            if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true when SameSite=None")
            if self.password_reset_dev_expose_token:
                raise ValueError("PASSWORD_RESET_DEV_EXPOSE_TOKEN must be false in production")
            if self.password_reset_dev_notice_enabled:
                raise ValueError("PASSWORD_RESET_DEV_NOTICE_ENABLED must be false in production")
            if not self.database_identity_check_enabled:
                raise ValueError("DATABASE_IDENTITY_CHECK_ENABLED must be true in production")
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
            "password_reset_enabled": self.password_reset_enabled,
            "password_reset_token_expire_minutes": self.password_reset_token_expire_minutes,
            "password_reset_max_active_tokens": self.password_reset_max_active_tokens,
            "password_reset_request_cooldown_seconds": self.password_reset_request_cooldown_seconds,
            "password_reset_delivery_provider": self.password_reset_delivery_provider,
            "password_reset_dev_notice_enabled": self.password_reset_dev_notice_enabled,
            "expected_application_id": self.expected_application_id,
            "expected_database_identity": self.expected_database_identity,
            "database_identity_check_enabled": self.database_identity_check_enabled,
            "llm_provider": self.llm_provider,
            "ollama_model": self.ollama_model,
            "ollama_keep_alive": self.ollama_keep_alive,
            "ollama_chat_num_predict": self.ollama_chat_num_predict,
            "ollama_chat_num_ctx": self.ollama_chat_num_ctx,
            "ollama_request_timeout_seconds": self.ollama_request_timeout_seconds,
            "ollama_first_token_timeout_seconds": self.ollama_first_token_timeout_seconds,
            "llm_max_input_characters": self.llm_max_input_characters,
            "llm_max_output_tokens": self.llm_max_output_tokens,
            "llm_default_temperature": self.llm_default_temperature,
            "document_upload_enabled": self.document_upload_enabled,
            "document_max_file_size_bytes": self.document_max_file_size_bytes,
            "document_allowed_extensions": self.document_allowed_extensions,
            "document_max_text_characters": self.document_max_text_characters,
            "document_max_chunks": self.document_max_chunks,
            "chunk_size_characters": self.chunk_size_characters,
            "chunk_overlap_characters": self.chunk_overlap_characters,
            "chunk_min_characters": self.chunk_min_characters,
            "embedding_provider": self.embedding_provider,
            "ollama_embedding_model": self.ollama_embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "embedding_batch_size": self.embedding_batch_size,
            "rag_default_top_k": self.rag_default_top_k,
            "rag_max_top_k": self.rag_max_top_k,
            "rag_min_similarity": self.rag_min_similarity,
            "conversation_max_history_messages": self.conversation_max_history_messages,
            "conversation_max_history_characters": self.conversation_max_history_characters,
            "conversation_max_context_characters": self.conversation_max_context_characters,
            "conversation_summary_trigger_messages": self.conversation_summary_trigger_messages,
            "conversation_summary_max_characters": self.conversation_summary_max_characters,
            "conversation_title_max_characters": self.conversation_title_max_characters,
            "message_max_characters": self.message_max_characters,
            "message_max_response_tokens": self.message_max_response_tokens,
            "chat_default_temperature": self.chat_default_temperature,
            "chat_default_top_k": self.chat_default_top_k,
            "conversation_search_max_results": self.conversation_search_max_results,
            "conversation_list_default_limit": self.conversation_list_default_limit,
            "conversation_list_max_limit": self.conversation_list_max_limit,
            "citation_excerpt_max_characters": self.citation_excerpt_max_characters,
            "conversation_auto_title_enabled": self.conversation_auto_title_enabled,
            "conversation_summary_enabled": self.conversation_summary_enabled,
            "chat_general_mode_enabled": self.chat_general_mode_enabled,
            "agent_tools_enabled": self.agent_tools_enabled,
            "agent_max_tool_iterations": self.agent_max_tool_iterations,
            "agent_tool_timeout_seconds": self.agent_tool_timeout_seconds,
            "agent_max_result_bytes": self.agent_max_result_bytes,
            "memory_enabled": self.memory_enabled,
            "memory_automatic_extraction_default": self.memory_automatic_extraction_default,
            "memory_suggestions_default": self.memory_suggestions_default,
            "memory_require_confirmation_default": self.memory_require_confirmation_default,
            "memory_max_active_per_user": self.memory_max_active_per_user,
            "memory_max_retrieval_results": self.memory_max_retrieval_results,
            "memory_max_content_characters": self.memory_max_content_characters,
            "memory_title_max_characters": self.memory_title_max_characters,
            "memory_context_max_characters": self.memory_context_max_characters,
            "memory_default_expiration_days": self.memory_default_expiration_days,
            "memory_min_relevance_score": self.memory_min_relevance_score,
            "memory_duplicate_similarity_threshold": self.memory_duplicate_similarity_threshold,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings. Call clear_settings_cache() in tests."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache (for tests)."""
    get_settings.cache_clear()
