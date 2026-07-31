"""Memory domain exceptions — safe client-facing messages only."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class MemoryError(AppError):
    """Base memory error."""


class MemoryNotFoundError(MemoryError):
    def __init__(self) -> None:
        super().__init__(
            code="memory_not_found",
            message="Memory not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class MemoryValidationError(MemoryError):
    def __init__(self, message: str, *, code: str = "memory_invalid") -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class MemorySensitiveContentError(MemoryError):
    def __init__(self, message: str = "Memory content appears sensitive and was rejected") -> None:
        super().__init__(
            code="memory_sensitive_content",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class MemoryLimitExceededError(MemoryError):
    def __init__(self, message: str = "Active memory limit reached") -> None:
        super().__init__(
            code="memory_limit_exceeded",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class MemoryDisabledError(MemoryError):
    def __init__(self, message: str = "Long-term memory is disabled") -> None:
        super().__init__(
            code="memory_disabled",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class MemoryConflictError(MemoryError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="memory_conflict",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class MemoryAmbiguousForgetError(MemoryError):
    def __init__(self, message: str, *, matches: list[dict[str, object]] | None = None) -> None:
        super().__init__(
            code="memory_ambiguous_forget",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=matches or [],
        )
