"""Admin memory endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.admin.schemas import AdminMemoryDetail, AdminMemoryListResponse
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep
from app.core.logging import request_id_ctx
from app.models.enums import MemoryCategory, MemorySource, MemoryStatus

router = APIRouter()


@router.get("/memories", response_model=AdminMemoryListResponse)
async def list_memories(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    owner_id: uuid.UUID | None = None,
    category: MemoryCategory | None = None,
    status: MemoryStatus | None = None,
    source: MemorySource | None = None,
) -> AdminMemoryListResponse:
    return await admin.list_memories(
        session,
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        category=category,
        status=status,
        source=source,
    )


@router.get("/memories/{memory_id}", response_model=AdminMemoryDetail)
async def get_memory(
    memory_id: uuid.UUID,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminMemoryDetail:
    return await admin.get_memory(session, memory_id)


@router.post("/memories/{memory_id}/archive", response_model=AdminMemoryDetail)
async def archive_memory(
    memory_id: uuid.UUID,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminMemoryDetail:
    return await admin.archive_memory(
        session,
        actor=admin_user,
        memory_id=memory_id,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/memories/{memory_id}/reject", response_model=AdminMemoryDetail)
async def reject_memory(
    memory_id: uuid.UUID,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminMemoryDetail:
    return await admin.reject_memory(
        session,
        actor=admin_user,
        memory_id=memory_id,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.delete("/memories/{memory_id}", status_code=204, response_class=Response)
async def delete_memory(
    memory_id: uuid.UUID,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> Response:
    await admin.delete_memory(
        session,
        actor=admin_user,
        memory_id=memory_id,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)
