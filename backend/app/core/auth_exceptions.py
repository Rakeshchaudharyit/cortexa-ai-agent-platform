"""Authentication and authorization domain exceptions."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError

_BEARER_HEADER = {"WWW-Authenticate": "Bearer"}


class EmailAlreadyRegisteredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="email_already_registered",
            message="An account with this email already exists",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidCredentialsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_credentials",
            message="Invalid email or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AccountDisabledError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="account_disabled",
            message="This account has been disabled",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class InvalidAccessTokenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_access_token",
            message="Invalid or expired access token",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers=_BEARER_HEADER,
        )


class InvalidRefreshTokenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_refresh_token",
            message="Invalid or expired refresh token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class RefreshTokenExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="refresh_token_expired",
            message="Invalid or expired refresh token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class RefreshTokenReuseDetectedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="refresh_token_reuse_detected",
            message="Invalid or expired refresh token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
