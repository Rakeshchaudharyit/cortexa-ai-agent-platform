"""Safe platform settings catalog and merge helpers."""

from __future__ import annotations

from typing import Any

from app.admin.exceptions import AdminValidationError
from app.admin.policies import SAFE_SETTING_KEYS, UNSAFE_SETTING_KEYS, is_safe_setting_key
from app.core.config import Settings

# Defaults for DB-backed display / operational overrides.
SETTING_DEFAULTS: dict[str, Any] = {
    "platform_display_name": "Cortexa AI Agent Platform",
    "support_email": "support@example.com",
    "default_timezone": "UTC",
    "maintenance_banner": "",
    "registration_enabled": True,
    "ai_default_temperature": None,  # falls back to runtime Settings
    "ai_max_output_tokens": None,
    "ai_keep_alive": None,
    "documents_allowed_extensions": None,
    "documents_max_file_size_bytes": None,
    "documents_chunk_size": None,
    "documents_chunk_overlap": None,
    "memory_enabled_default": None,
    "memory_suggestions_default": None,
    "memory_automatic_extraction_default": None,
    "memory_confirmation_default": None,
    "tools_global_enabled": True,
}


def validate_setting_value(key: str, value: Any) -> Any:
    """Validate and normalize a single allowlisted setting value."""
    if not is_safe_setting_key(key):
        raise AdminValidationError(f"Setting key '{key}' is not editable")

    if key == "platform_display_name":
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise AdminValidationError(
                "platform_display_name must be a non-empty string ≤ 120 chars"
            )
        return value.strip()
    if key == "support_email":
        if not isinstance(value, str) or "@" not in value or len(value) > 320:
            raise AdminValidationError("support_email must be a valid email-like string")
        return value.strip().lower()
    if key == "default_timezone":
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise AdminValidationError("default_timezone must be a non-empty string ≤ 64 chars")
        return value.strip()
    if key == "maintenance_banner":
        if value is None:
            return ""
        if not isinstance(value, str) or len(value) > 500:
            raise AdminValidationError("maintenance_banner must be a string ≤ 500 chars")
        return value
    if key in {
        "registration_enabled",
        "tools_global_enabled",
        "memory_enabled_default",
        "memory_suggestions_default",
        "memory_automatic_extraction_default",
        "memory_confirmation_default",
    }:
        if not isinstance(value, bool):
            raise AdminValidationError(f"{key} must be a boolean")
        return value
    if key == "ai_default_temperature":
        if value is None:
            return None
        if not isinstance(value, int | float) or not 0.0 <= float(value) <= 2.0:
            raise AdminValidationError("ai_default_temperature must be between 0 and 2")
        return float(value)
    if key == "ai_max_output_tokens":
        if value is None:
            return None
        if not isinstance(value, int) or not 16 <= value <= 8192:
            raise AdminValidationError(
                "ai_max_output_tokens must be an integer between 16 and 8192"
            )
        return value
    if key == "ai_keep_alive":
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip() or len(value) > 32:
            raise AdminValidationError("ai_keep_alive must be a short duration string")
        return value.strip()
    if key == "documents_allowed_extensions":
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise AdminValidationError(
                "documents_allowed_extensions must be a comma-separated string"
            )
        parts = [p.strip().lower() for p in value.split(",") if p.strip()]
        if not parts or any(not p.startswith(".") for p in parts):
            raise AdminValidationError("Each extension must start with '.'")
        return ",".join(parts)
    if key == "documents_max_file_size_bytes":
        if value is None:
            return None
        if not isinstance(value, int) or not 1024 <= value <= 50_000_000:
            raise AdminValidationError("documents_max_file_size_bytes must be between 1KB and 50MB")
        return value
    if key in {"documents_chunk_size", "documents_chunk_overlap"}:
        if value is None:
            return None
        if not isinstance(value, int) or value < 0 or value > 20_000:
            raise AdminValidationError(f"{key} must be an integer between 0 and 20000")
        return value

    raise AdminValidationError(f"Unsupported setting key '{key}'")


def runtime_settings_snapshot(settings: Settings) -> dict[str, Any]:
    """Safe read-only view of runtime configuration for admins."""
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "app_env": settings.app_env,
        "password_min_length": settings.password_min_length,
        "access_token_expire_minutes": settings.access_token_expire_minutes,
        "refresh_token_expire_days": settings.refresh_token_expire_days,
        "password_reset_enabled": settings.password_reset_enabled,
        "llm_provider": settings.llm_provider,
        "ollama_model": settings.ollama_model,
        "embedding_provider": settings.embedding_provider,
        "ollama_embedding_model": settings.ollama_embedding_model,
        "llm_default_temperature": settings.llm_default_temperature,
        "llm_max_output_tokens": settings.llm_max_output_tokens,
        "ollama_keep_alive": settings.ollama_keep_alive,
        "ollama_chat_num_ctx": settings.ollama_chat_num_ctx,
        "ollama_chat_num_predict": settings.ollama_chat_num_predict,
        "document_allowed_extensions": settings.document_allowed_extensions,
        "document_max_file_size_bytes": settings.document_max_file_size_bytes,
        "chunk_size_characters": settings.chunk_size_characters,
        "chunk_overlap_characters": settings.chunk_overlap_characters,
        "memory_enabled": settings.memory_enabled,
        "memory_suggestions_default": settings.memory_suggestions_default,
        "memory_automatic_extraction_default": settings.memory_automatic_extraction_default,
        "memory_require_confirmation_default": settings.memory_require_confirmation_default,
        "expected_database_identity": settings.expected_database_identity,
    }


def merge_effective_settings(
    settings: Settings,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge runtime defaults with DB overrides for admin display."""
    base = dict(SETTING_DEFAULTS)
    base["platform_display_name"] = settings.app_name
    base["ai_default_temperature"] = settings.llm_default_temperature
    base["ai_max_output_tokens"] = settings.llm_max_output_tokens
    base["ai_keep_alive"] = settings.ollama_keep_alive
    base["documents_allowed_extensions"] = settings.document_allowed_extensions
    base["documents_max_file_size_bytes"] = settings.document_max_file_size_bytes
    base["documents_chunk_size"] = settings.chunk_size_characters
    base["documents_chunk_overlap"] = settings.chunk_overlap_characters
    base["memory_enabled_default"] = settings.memory_enabled
    base["memory_suggestions_default"] = settings.memory_suggestions_default
    base["memory_automatic_extraction_default"] = settings.memory_automatic_extraction_default
    base["memory_confirmation_default"] = settings.memory_require_confirmation_default

    for key, value in overrides.items():
        if key in SAFE_SETTING_KEYS and key not in UNSAFE_SETTING_KEYS:
            base[key] = value
    return base
