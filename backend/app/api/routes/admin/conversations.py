"""Admin conversation endpoints (metadata + controlled lifecycle)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.admin.schemas import (
    AdminConversationDeletionImpact,
    AdminConversationDetail,
    AdminConversationListResponse,
    AdminDestructiveConfirmRequest,
)
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep
from app.core.logging import request_id_ctx
from app.models.enums import ConversationStatus

router = APIRouter()


@router.get("/conversations", response_model=AdminConversationListResponse)
async def list_conversations(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    owner_id: uuid.UUID | None = None,
    status: ConversationStatus | None = None,
    activity_from: datetime | None = None,
    activity_to: datetime | None = None,
    grounded: bool | None = None,
) -> AdminConversationListResponse:
    return await admin.list_conversations(
        session,
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        status=status,
        activity_from=activity_from,
        activity_to=activity_to,
        grounded=grounded,
    )


@router.get("/conversations/{conversation_id}", response_model=AdminConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminConversationDetail:
    return await admin.get_conversation(session, conversation_id)


@router.get(
    "/conversations/{conversation_id}/deletion-impact",
    response_model=AdminConversationDeletionImpact,
)
async def get_conversation_deletion_impact(
    conversation_id: uuid.UUID,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminConversationDeletionImpact:
    return await admin.get_conversation_deletion_impact(session, conversation_id)


@router.post(
    "/conversations/{conversation_id}/archive",
    response_model=AdminConversationDetail,
)
async def archive_conversation(
    conversation_id: uuid.UUID,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminConversationDetail:
    return await admin.archive_conversation(
        session,
        actor=admin_user,
        conversation_id=conversation_id,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.delete("/conversations/{conversation_id}", status_code=204, response_class=Response)
async def delete_conversation(
    conversation_id: uuid.UUID,
    body: AdminDestructiveConfirmRequest,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> Response:
    await admin.delete_conversation(
        session,
        actor=admin_user,
        conversation_id=conversation_id,
        confirm=body.confirm,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)
