"""Admin platform settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.admin.schemas import (
    AdminSettingsResponse,
    AdminSettingsUpdateRequest,
    AdminSettingsUpdateResponse,
)
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep
from app.core.logging import request_id_ctx

router = APIRouter()


@router.get("/settings", response_model=AdminSettingsResponse)
async def get_settings(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminSettingsResponse:
    return await admin.get_settings(session)


@router.patch("/settings", response_model=AdminSettingsUpdateResponse)
async def update_settings(
    body: AdminSettingsUpdateRequest,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminSettingsUpdateResponse:
    return await admin.update_settings(
        session,
        actor=admin_user,
        updates=body.updates,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
