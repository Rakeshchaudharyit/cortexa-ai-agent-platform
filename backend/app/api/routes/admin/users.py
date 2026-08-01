"""Admin user management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.admin.schemas import (
    AdminRevokeSessionsResponse,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserUpdateRequest,
    AdminUserUpdateResponse,
)
from app.api.deps import AdminServiceDep, CurrentActiveUser, CurrentAdminUser, DbSessionDep
from app.core.logging import request_id_ctx
from app.models.enums import UserRole, UserStatus

router = APIRouter()


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: str | None = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    verified: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminUserListResponse:
    _ = admin_user
    return await admin.list_users(
        session,
        limit=limit,
        offset=offset,
        search=search,
        role=role,
        status=status,
        verified=verified,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: uuid.UUID,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminUserDetail:
    _ = admin_user
    return await admin.get_user(session, user_id)


@router.patch("/users/{user_id}", response_model=AdminUserUpdateResponse)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdateRequest,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminUserUpdateResponse:
    ip, ua = _client_meta(request)
    return await admin.update_user(
        session,
        actor=admin_user,
        user_id=user_id,
        role=body.role,
        status=body.status,
        request_id=request_id_ctx.get(),
        ip_address=ip,
        user_agent=ua,
    )


@router.post("/users/{user_id}/revoke-sessions", response_model=AdminRevokeSessionsResponse)
async def revoke_sessions(
    user_id: uuid.UUID,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminRevokeSessionsResponse:
    ip, ua = _client_meta(request)
    return await admin.revoke_user_sessions(
        session,
        actor=admin_user,
        user_id=user_id,
        request_id=request_id_ctx.get(),
        ip_address=ip,
        user_agent=ua,
    )

@router.post("/session/acknowledge", status_code=204, response_class=Response)
async def acknowledge_admin_session(
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> Response:
    ip, ua = _client_meta(request)
    await admin.record_admin_login_success(
        session,
        actor=admin_user,
        request_id=request_id_ctx.get(),
        ip_address=ip,
        user_agent=ua,
    )
    return Response(status_code=204)


@router.post("/session/denied", status_code=204, response_class=Response)
async def record_denied_admin_session(
    request: Request,
    user: CurrentActiveUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> Response:
    ip, ua = _client_meta(request)
    await admin.record_admin_login_denied(
        session,
        actor=user,
        request_id=request_id_ctx.get(),
        ip_address=ip,
        user_agent=ua,
    )
    return Response(status_code=204)
