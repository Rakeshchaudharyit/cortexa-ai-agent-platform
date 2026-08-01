"""Admin conversation endpoints (metadata only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.admin.schemas import AdminConversationDetail, AdminConversationListResponse
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep
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
