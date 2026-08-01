"""Admin-domain exceptions mapped to safe client responses."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class AdminNotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(
            code="not_found",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class AdminValidationError(AppError):
    def __init__(self, message: str, *, details: list[dict[str, object]] | None = None) -> None:
        super().__init__(
            code="validation_error",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details or [],
        )


class AdminConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="conflict",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class LastAdminProtectionError(AppError):
    def __init__(
        self,
        message: str = "Cannot remove or disable the last active admin account",
    ) -> None:
        super().__init__(
            code="last_admin_protected",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )
