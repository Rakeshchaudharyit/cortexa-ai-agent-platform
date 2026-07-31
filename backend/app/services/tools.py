"""Tool listing and execution history service with ownership enforcement."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import UserRole
from app.models.tool_execution import ToolExecution
from app.models.user import User
from app.tools.executor import redact_mapping
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    ToolDefinitionResponse,
    ToolExecutionDetail,
    ToolExecutionListResponse,
    ToolExecutionSummary,
    ToolListResponse,
)


def _summary_from_mapping(value: dict[str, Any] | None, *, limit: int = 8) -> dict[str, Any] | None:
    if not value:
        return None
    safe = redact_mapping(value)
    if not isinstance(safe, dict):
        return {"value": safe}
    items = list(safe.items())[:limit]
    return {str(k): v for k, v in items}


def execution_to_summary(row: ToolExecution) -> ToolExecutionSummary:
    return ToolExecutionSummary(
        id=row.id,
        tool_name=row.tool_name,
        tool_version=row.tool_version,
        status=row.status.value,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        arguments_summary=_summary_from_mapping(row.arguments_json),
        result_summary=_summary_from_mapping(row.result_json),
        error_code=row.error_code,
        error_message=row.error_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        duration_ms=row.duration_ms,
        created_at=row.created_at,
    )


def execution_to_detail(row: ToolExecution) -> ToolExecutionDetail:
    base = execution_to_summary(row)
    return ToolExecutionDetail(
        **base.model_dump(),
        arguments_json=redact_mapping(row.arguments_json)
        if isinstance(row.arguments_json, dict)
        else row.arguments_json,
        result_json=redact_mapping(row.result_json)
        if isinstance(row.result_json, dict)
        else row.result_json,
        correlation_id=row.correlation_id,
    )


class ToolService:
    """Authenticated tool discovery and owned execution history."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def list_tools_for_user(self, user: User) -> ToolListResponse:
        tools = self.registry.list_enabled(role=user.role)
        items = [
            ToolDefinitionResponse(
                name=tool.name,
                description=tool.description,
                version=tool.version,
                category=tool.category,
                requires_confirmation=tool.requires_confirmation,
                enabled=tool.enabled,
                parameters=tool.to_spec().parameters,
            )
            for tool in tools
        ]
        return ToolListResponse(tools=items, total=len(items))

    def list_all_tools_admin(self, user: User) -> ToolListResponse:
        if user.role != UserRole.admin:
            raise AppError(
                code="forbidden",
                message="Insufficient permissions",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        items = [
            ToolDefinitionResponse(
                name=tool.name,
                description=tool.description,
                version=tool.version,
                category=tool.category,
                requires_confirmation=tool.requires_confirmation,
                enabled=tool.enabled,
                parameters=tool.to_spec().parameters,
            )
            for tool in self.registry.list_all()
        ]
        return ToolListResponse(tools=items, total=len(items))

    async def list_executions(
        self,
        session: AsyncSession,
        user: User,
        *,
        limit: int = 20,
        offset: int = 0,
        conversation_id: uuid.UUID | None = None,
    ) -> ToolExecutionListResponse:
        filters = [ToolExecution.user_id == user.id]
        if conversation_id is not None:
            filters.append(ToolExecution.conversation_id == conversation_id)
        total = int(
            await session.scalar(select(func.count()).select_from(ToolExecution).where(*filters))
            or 0
        )
        result = await session.scalars(
            select(ToolExecution)
            .where(*filters)
            .order_by(ToolExecution.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list(result.all())
        return ToolExecutionListResponse(
            items=[execution_to_summary(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_execution(
        self,
        session: AsyncSession,
        user: User,
        execution_id: uuid.UUID,
    ) -> ToolExecutionDetail:
        row = await session.scalar(select(ToolExecution).where(ToolExecution.id == execution_id))
        if row is None or row.user_id != user.id:
            raise AppError(
                code="tool_execution_not_found",
                message="Tool execution not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return execution_to_detail(row)

    async def list_for_message(
        self,
        session: AsyncSession,
        user: User,
        message_id: uuid.UUID,
    ) -> list[ToolExecutionSummary]:
        result = await session.scalars(
            select(ToolExecution)
            .where(
                ToolExecution.user_id == user.id,
                ToolExecution.message_id == message_id,
            )
            .order_by(ToolExecution.created_at.asc())
        )
        return [execution_to_summary(row) for row in result.all()]
