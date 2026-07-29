"""Password-reset domain exceptions."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class PasswordResetDisabledError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="password_reset_disabled",
            message="Password reset is currently unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class PasswordResetTokenInvalidError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="password_reset_token_invalid",
            message="This password reset link is invalid or has expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class PasswordResetTokenExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="password_reset_token_expired",
            message="This password reset link is invalid or has expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class PasswordResetTokenUsedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="password_reset_token_used",
            message="This password reset link is invalid or has expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class PasswordResetPasswordMismatchError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="password_reset_password_mismatch",
            message="Passwords do not match",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class PasswordResetRateLimitedError(AppError):
    def __init__(self) -> None:
        # Public forgot-password never surfaces this; reserved for internal/policy use.
        super().__init__(
            code="password_reset_rate_limited",
            message=(
                "If an account exists for that email, "
                "password reset instructions have been prepared."
            ),
            status_code=status.HTTP_200_OK,
        )


class PasswordResetDeliveryError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="password_reset_delivery_error",
            message="Password reset is temporarily unavailable. Please try again later.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
