"""Storage provider exceptions."""

from __future__ import annotations

from app.core.exceptions import AppError


class StorageError(AppError):
    """Base storage error."""

    def __init__(
        self,
        message: str = "Document storage operation failed",
        *,
        code: str = "storage_error",
        status_code: int = 500,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code)


class StorageNotFoundError(StorageError):
    def __init__(self, message: str = "Stored document file was not found") -> None:
        super().__init__(message=message, code="storage_not_found", status_code=404)


class StorageConflictError(StorageError):
    def __init__(self, message: str = "Document storage key already exists") -> None:
        super().__init__(message=message, code="storage_conflict", status_code=409)
