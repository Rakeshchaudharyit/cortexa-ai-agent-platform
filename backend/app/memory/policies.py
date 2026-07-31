"""Memory policy helpers — confirmation, limits, conflicts, extraction rules."""

from __future__ import annotations

from app.core.config import Settings
from app.models.enums import MemoryCategory, MemoryConfidence, MemorySource, MemoryStatus

CONFLICT_CATEGORIES = frozenset(
    {
        MemoryCategory.preference,
        MemoryCategory.instruction,
    }
)

# Categories that may be auto-suggested when extraction is enabled.
EXTRACTABLE_CATEGORIES = frozenset(
    {
        MemoryCategory.preference,
        MemoryCategory.project,
        MemoryCategory.technical_context,
        MemoryCategory.instruction,
        MemoryCategory.workflow,
        MemoryCategory.decision,
        MemoryCategory.goal,
        MemoryCategory.personal_context,
        MemoryCategory.other,
    }
)


def default_settings_values(settings: Settings) -> dict[str, object]:
    return {
        "memory_enabled": settings.memory_enabled,
        "automatic_extraction_enabled": settings.memory_automatic_extraction_default,
        "suggestions_enabled": settings.memory_suggestions_default,
        "require_confirmation": settings.memory_require_confirmation_default,
        "include_memories_in_chat": True,
        "maximum_active_memories": settings.memory_max_active_per_user,
        "default_expiration_days": settings.memory_default_expiration_days,
    }


def should_require_confirmation(
    *,
    source: MemorySource,
    require_confirmation_setting: bool,
    confidence: MemoryConfidence | None = None,
) -> bool:
    if source == MemorySource.explicit_user_request:
        # Explicit remember may skip confirmation when user setting allows.
        return bool(require_confirmation_setting)
    if source in {MemorySource.assistant_suggestion, MemorySource.automatic_extraction}:
        return True
    if confidence == MemoryConfidence.low:
        return True
    return bool(require_confirmation_setting)


def initial_status_for_create(*, confirmation_required: bool) -> MemoryStatus:
    return MemoryStatus.proposed if confirmation_required else MemoryStatus.active


def is_preference_conflict(existing_category: MemoryCategory, new_category: MemoryCategory) -> bool:
    return existing_category in CONFLICT_CATEGORIES and new_category in CONFLICT_CATEGORIES


def may_extract_automatically(*, memory_enabled: bool, automatic_extraction_enabled: bool) -> bool:
    return memory_enabled and automatic_extraction_enabled


def may_suggest(*, memory_enabled: bool, suggestions_enabled: bool) -> bool:
    return memory_enabled and suggestions_enabled


def conversation_memory_active(
    *,
    global_enabled: bool,
    include_in_chat: bool,
    conversation_override: bool | None,
) -> bool:
    if conversation_override is False:
        return False
    if conversation_override is True:
        return global_enabled and include_in_chat
    return global_enabled and include_in_chat
