"""Authenticated long-term memory management APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import Response

from app.api.deps import CurrentActiveUser, DbSessionDep, MemoryServiceDep
from app.memory.schemas import (
    MemoryAuditListResponse,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    MemorySettingsResponse,
    MemorySettingsUpdateRequest,
    MemoryUpdateRequest,
)
from app.models.enums import MemoryCategory, MemoryStatus

router = APIRouter(tags=["memories"])


@router.get(
    "/memories",
    response_model=MemoryListResponse,
    summary="List the current user's long-term memories",
)
async def list_memories(
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: MemoryStatus | None = None,
    category: MemoryCategory | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> MemoryListResponse:
    return await memories.list_memories(
        session,
        user,
        status=status,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/memories",
    response_model=MemoryResponse,
    summary="Create a long-term memory",
)
async def create_memory(
    body: MemoryCreateRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemoryResponse:
    memory = await memories.create_memory(session, user, body)
    await session.commit()
    return memories.to_response(memory)


@router.get(
    "/memories/{memory_id}",
    response_model=MemoryResponse,
    summary="Get a memory owned by the current user",
)
async def get_memory(
    memory_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemoryResponse:
    return await memories.get_memory(session, user, memory_id)


@router.patch(
    "/memories/{memory_id}",
    response_model=MemoryResponse,
    summary="Update a memory owned by the current user",
)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdateRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemoryResponse:
    result = await memories.update_memory(session, user, memory_id, body)
    await session.commit()
    return result


@router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Soft-delete a memory (content redacted)",
)
async def delete_memory(
    memory_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> Response:
    await memories.delete_memory(session, user, memory_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/memories/{memory_id}/confirm",
    response_model=MemoryResponse,
    summary="Confirm a proposed memory",
)
async def confirm_memory(
    memory_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemoryResponse:
    result = await memories.confirm(session, user, memory_id)
    await session.commit()
    return result


@router.post(
    "/memories/{memory_id}/archive",
    response_model=MemoryResponse,
    summary="Archive an active memory",
)
async def archive_memory(
    memory_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemoryResponse:
    result = await memories.archive(session, user, memory_id)
    await session.commit()
    return result


@router.post(
    "/memories/{memory_id}/restore",
    response_model=MemoryResponse,
    summary="Restore an archived memory",
)
async def restore_memory(
    memory_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemoryResponse:
    result = await memories.restore(session, user, memory_id)
    await session.commit()
    return result


@router.post(
    "/memories/{memory_id}/reject",
    response_model=MemoryResponse,
    summary="Reject a proposed memory",
)
async def reject_memory(
    memory_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemoryResponse:
    result = await memories.reject(session, user, memory_id)
    await session.commit()
    return result


@router.get(
    "/memory-settings",
    response_model=MemorySettingsResponse,
    summary="Get the current user's memory settings",
)
async def get_memory_settings(
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemorySettingsResponse:
    return await memories.get_settings(session, user)


@router.patch(
    "/memory-settings",
    response_model=MemorySettingsResponse,
    summary="Update the current user's memory settings",
)
async def update_memory_settings(
    body: MemorySettingsUpdateRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
) -> MemorySettingsResponse:
    result = await memories.update_settings(session, user, body)
    await session.commit()
    return result


@router.get(
    "/memory-audit",
    response_model=MemoryAuditListResponse,
    summary="List safe memory audit events for the current user",
)
async def list_memory_audit(
    session: DbSessionDep,
    user: CurrentActiveUser,
    memories: MemoryServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemoryAuditListResponse:
    from app.memory.schemas import MemoryAuditEventResponse, MemoryAuditListResponse

    items, total = await memories.repository.list_audit(session, user, limit=limit, offset=offset)
    return MemoryAuditListResponse(
        items=[MemoryAuditEventResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
