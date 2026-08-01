"""Admin audit log endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.admin.schemas import AdminAuditListResponse
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep

router = APIRouter()


@router.get("/audit", response_model=AdminAuditListResponse)
async def list_audit(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    target_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminAuditListResponse:
    return await admin.list_audit(
        session,
        limit=limit,
        offset=offset,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        created_from=created_from,
        created_to=created_to,
    )
