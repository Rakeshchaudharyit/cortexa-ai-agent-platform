"""Authentication FastAPI dependencies."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_exceptions import InvalidAccessTokenError
from app.core.config import Settings
from app.db.session import get_db_session
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import AuthService

logger = logging.getLogger("cortexa.auth.deps")

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings_dep(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are not configured")
    return settings


def get_auth_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if isinstance(service, AuthService):
        return service
    settings = get_settings_dep(request)
    created = AuthService.from_settings(settings)
    request.app.state.auth_service = created
    return created


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidAccessTokenError()
    token = credentials.credentials.strip()
    if not token:
        raise InvalidAccessTokenError()

    claims = auth_service.tokens.decode_access_token(token)
    user = await auth_service.get_user_by_id(session, claims.subject)
    if user is None:
        raise InvalidAccessTokenError()
    return user


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    return auth_service.ensure_active(user)


def require_role(*roles: UserRole) -> Callable[..., Any]:
    """Foundational role gate — admin UI is not implemented in Phase 3."""

    allowed = frozenset(roles)

    async def _dependency(
        user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if user.role not in allowed:
            from app.core.exceptions import AppError

            raise AppError(
                code="forbidden",
                message="Insufficient permissions",
                status_code=403,
            )
        return user

    return _dependency


CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
