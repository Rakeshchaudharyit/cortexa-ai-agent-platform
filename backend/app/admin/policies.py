"""Admin authorization and settings safety policies."""

from __future__ import annotations

from typing import Any

ADMIN_PAGE_DEFAULT = 20
ADMIN_PAGE_MAX = 100

# Keys that may never be stored or edited via the admin settings API.
UNSAFE_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "jwt_secret_key",
        "postgres_password",
        "database_url",
        "redis_url",
        "auth_cookie_name",
        "admin_user_cli_allow_production",
        "legacy_db_migration_allow_production",
        "password_reset_dev_expose_token",
        "ollama_base_url",
        "expected_application_id",
        "expected_database_identity",
        "database_identity_check_enabled",
        "app_env",
        "app_debug",
    }
)

# Allowlisted editable / visible platform setting keys (DB overrides).
SAFE_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "platform_display_name",
        "support_email",
        "default_timezone",
        "maintenance_banner",
        "registration_enabled",
        "ai_default_temperature",
        "ai_max_output_tokens",
        "ai_keep_alive",
        "documents_allowed_extensions",
        "documents_max_file_size_bytes",
        "documents_chunk_size",
        "documents_chunk_overlap",
        "memory_enabled_default",
        "memory_suggestions_default",
        "memory_automatic_extraction_default",
        "memory_confirmation_default",
        "tools_global_enabled",
    }
)

# Read-only keys exposed from runtime Settings (never writable via admin).
RUNTIME_READONLY_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "password_min_length",
        "access_token_expire_minutes",
        "refresh_token_expire_days",
        "password_reset_enabled",
        "llm_provider",
        "ollama_model",
        "embedding_provider",
        "ollama_embedding_model",
        "llm_default_temperature",
        "llm_max_output_tokens",
        "ollama_keep_alive",
        "document_allowed_extensions",
        "document_max_file_size_bytes",
        "chunk_size_characters",
        "chunk_overlap_characters",
        "memory_enabled",
        "memory_suggestions_default",
        "memory_automatic_extraction_default",
        "memory_require_confirmation_default",
    }
)


def is_safe_setting_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in UNSAFE_SETTING_KEYS:
        return False
    return normalized in SAFE_SETTING_KEYS


def clamp_page_size(limit: int | None, *, default: int = ADMIN_PAGE_DEFAULT) -> int:
    value = default if limit is None else int(limit)
    if value < 1:
        return 1
    return min(value, ADMIN_PAGE_MAX)


def sanitize_audit_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip obviously sensitive keys from audit metadata."""
    if not metadata:
        return None
    blocked = (
        "password",
        "token",
        "secret",
        "hash",
        "cookie",
        "authorization",
        "api_key",
        "jwt",
        "content",
        "embedding",
        "stack",
        "traceback",
    )
    safe: dict[str, Any] = {}
    for key, value in list(metadata.items())[:40]:
        key_l = str(key).lower()
        if any(part in key_l for part in blocked):
            continue
        if isinstance(value, str) and len(value) > 500:
            safe[str(key)] = value[:500] + "…"
        elif isinstance(value, str | int | float | bool) or value is None:
            safe[str(key)] = value
        elif isinstance(value, list):
            safe[str(key)] = value[:20]
        elif isinstance(value, dict):
            nested = sanitize_audit_metadata(value)
            if nested:
                safe[str(key)] = nested
    return safe or None
