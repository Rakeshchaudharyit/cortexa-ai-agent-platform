"""Authentication API routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    AuthServiceDep,
    CurrentActiveUser,
    DbSessionDep,
    SettingsDep,
)
from app.core.config import Settings
from app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    UserPublic,
)

logger = logging.getLogger("cortexa.api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Structured so production rate limiting can wrap these handlers later.
# Login, registration, and refresh MUST be rate-limited in production.


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def _set_refresh_cookie(
    response: Response,
    *,
    settings: Settings,
    refresh_token: str,
    expires_at: datetime,
) -> None:
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=refresh_token,
        max_age=max_age,
        expires=expires_at,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    session: DbSessionDep,
    auth_service: AuthServiceDep,
    settings: SettingsDep,
) -> AuthTokenResponse:
    result = await auth_service.register(
        session,
        email=str(body.email),
        password=body.password,
        full_name=body.full_name,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(
        response,
        settings=settings,
        refresh_token=result.refresh_token,
        expires_at=result.refresh_expires_at,
    )
    return result.response


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    summary="Authenticate with email and password",
)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    session: DbSessionDep,
    auth_service: AuthServiceDep,
    settings: SettingsDep,
) -> AuthTokenResponse:
    result = await auth_service.login(
        session,
        email=str(body.email),
        password=body.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(
        response,
        settings=settings,
        refresh_token=result.refresh_token,
        expires_at=result.refresh_expires_at,
    )
    return result.response


@router.post(
    "/refresh",
    response_model=AuthTokenResponse,
    summary="Rotate refresh session and issue a new access token",
)
async def refresh(
    request: Request,
    response: Response,
    session: DbSessionDep,
    auth_service: AuthServiceDep,
    settings: SettingsDep,
) -> AuthTokenResponse:
    raw = request.cookies.get(settings.auth_cookie_name)
    if not raw:
        from app.core.auth_exceptions import InvalidRefreshTokenError

        raise InvalidRefreshTokenError()
    result = await auth_service.refresh(
        session,
        raw_refresh_token=raw,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(
        response,
        settings=settings,
        refresh_token=result.refresh_token,
        expires_at=result.refresh_expires_at,
    )
    return result.response


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke the current refresh session and clear the cookie",
)
async def logout(
    request: Request,
    response: Response,
    session: DbSessionDep,
    auth_service: AuthServiceDep,
    settings: SettingsDep,
) -> MessageResponse:
    raw = request.cookies.get(settings.auth_cookie_name)
    await auth_service.logout(session, raw_refresh_token=raw)
    _clear_refresh_cookie(response, settings=settings)
    return MessageResponse(message="Logged out")


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Return the authenticated user profile",
)
async def me(user: CurrentActiveUser) -> UserPublic:
    return UserPublic.model_validate(user)
