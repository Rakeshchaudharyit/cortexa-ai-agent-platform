"""Long-term memory package — persistence foundation (Phase 7)."""

from __future__ import annotations

from app.memory.exceptions import (
    MemoryAmbiguousForgetError,
    MemoryDisabledError,
    MemoryError,
    MemoryLimitExceededError,
    MemoryNotFoundError,
    MemorySensitiveContentError,
    MemoryValidationError,
)
from app.memory.policies import default_settings_values, should_require_confirmation
from app.memory.repository import MemoryRepository
from app.memory.schemas import (
    MemoryCandidate,
    MemoryContextBlock,
    MemoryCreateRequest,
    MemoryIntentKind,
    MemoryIntentResult,
    MemoryListResponse,
    MemoryResponse,
    MemorySettingsResponse,
    MemorySettingsUpdateRequest,
    RetrievedMemoryView,
)

__all__ = [
    "MemoryAmbiguousForgetError",
    "MemoryCandidate",
    "MemoryContextBlock",
    "MemoryCreateRequest",
    "MemoryDisabledError",
    "MemoryError",
    "MemoryIntentKind",
    "MemoryIntentResult",
    "MemoryLimitExceededError",
    "MemoryListResponse",
    "MemoryNotFoundError",
    "MemoryRepository",
    "MemoryResponse",
    "MemorySensitiveContentError",
    "MemorySettingsResponse",
    "MemorySettingsUpdateRequest",
    "MemoryValidationError",
    "RetrievedMemoryView",
    "default_settings_values",
    "should_require_confirmation",
]
