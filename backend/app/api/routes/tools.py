"""Authenticated tool discovery and execution history APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentActiveUser, DbSessionDep, ToolServiceDep
from app.tools.schemas import (
    ToolExecutionDetail,
    ToolExecutionListResponse,
    ToolListResponse,
)

router = APIRouter(tags=["tools"])


@router.get(
    "/tools",
    response_model=ToolListResponse,
    summary="List tools available to the current user",
)
async def list_tools(
    user: CurrentActiveUser,
    tools: ToolServiceDep,
) -> ToolListResponse:
    return tools.list_tools_for_user(user)


@router.get(
    "/tool-executions",
    response_model=ToolExecutionListResponse,
    summary="List the current user's tool executions",
)
async def list_tool_executions(
    session: DbSessionDep,
    user: CurrentActiveUser,
    tools: ToolServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    conversation_id: uuid.UUID | None = None,
) -> ToolExecutionListResponse:
    return await tools.list_executions(
        session,
        user,
        limit=limit,
        offset=offset,
        conversation_id=conversation_id,
    )


@router.get(
    "/tool-executions/{execution_id}",
    response_model=ToolExecutionDetail,
    summary="Get a tool execution owned by the current user",
)
async def get_tool_execution(
    execution_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    tools: ToolServiceDep,
) -> ToolExecutionDetail:
    return await tools.get_execution(session, user, execution_id)
