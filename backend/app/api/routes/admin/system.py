"""Admin system health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.admin.schemas import AdminSystemHealthResponse
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep

router = APIRouter()


@router.get("/system", response_model=AdminSystemHealthResponse)
async def system_health(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminSystemHealthResponse:
    return await admin.get_system_health(session)
