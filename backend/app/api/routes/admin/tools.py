"""Admin tool and tool-execution endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.admin.schemas import (
    AdminToolExecutionDetail,
    AdminToolExecutionListResponse,
    AdminToolListResponse,
    AdminToolUpdateRequest,
    AdminToolUpdateResponse,
)
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep
from app.core.logging import request_id_ctx
from app.models.enums import ToolExecutionStatus

router = APIRouter()


@router.get("/tools", response_model=AdminToolListResponse)
async def list_tools(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminToolListResponse:
    return await admin.list_tools(session)


@router.patch("/tools/{tool_name}", response_model=AdminToolUpdateResponse)
async def update_tool(
    tool_name: str,
    body: AdminToolUpdateRequest,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminToolUpdateResponse:
    return await admin.update_tool(
        session,
        actor=admin_user,
        tool_name=tool_name,
        enabled=body.enabled,
        timeout_override=body.timeout_override,
        confirmation_required_override=body.confirmation_required_override,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.delete("/tools/{tool_name}/configuration", response_model=AdminToolUpdateResponse)
async def reset_tool_configuration(
    tool_name: str,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminToolUpdateResponse:
    return await admin.reset_tool_configuration(
        session,
        actor=admin_user,
        tool_name=tool_name,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/tool-executions", response_model=AdminToolExecutionListResponse)
async def list_tool_executions(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    user_id: uuid.UUID | None = None,
    tool_name: str | None = None,
    status: ToolExecutionStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminToolExecutionListResponse:
    return await admin.list_tool_executions(
        session,
        limit=limit,
        offset=offset,
        user_id=user_id,
        tool_name=tool_name,
        status=status,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/tool-executions/{execution_id}", response_model=AdminToolExecutionDetail)
async def get_tool_execution(
    execution_id: uuid.UUID,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminToolExecutionDetail:
    return await admin.get_tool_execution(session, execution_id)
