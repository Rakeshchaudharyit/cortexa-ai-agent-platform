"""Centralized tool executor with auth, validation, timeout, persistence, and redaction."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.enums import ToolExecutionStatus, UserRole
from app.models.tool_execution import ToolExecution
from app.tools.base import BaseTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import (
    ToolConfirmationRequiredError,
    ToolDisabledError,
    ToolError,
    ToolExecutionFailedError,
    ToolInvalidArgumentsError,
    ToolNotFoundError,
    ToolPermissionDeniedError,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolResultPayload

logger = logging.getLogger("cortexa.tools.executor")

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "refresh_token",
        "access_token",
        "cookie",
        "jwt",
    }
)


def redact_mapping(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact sensitive keys from mappings/lists."""
    if depth > 8:
        return "[truncated]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if any(s in key_l for s in _SENSITIVE_KEYS):
                out[str(key)] = "[redacted]"
            else:
                out[str(key)] = redact_mapping(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [redact_mapping(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str) and len(value) > 4_000:
        return value[:4_000] + "…"
    return value


def truncate_json(value: Any, *, max_bytes: int) -> Any:
    """Ensure JSON-serialized payload stays within max_bytes."""
    raw = json.dumps(value, default=str, ensure_ascii=False)
    if len(raw.encode("utf-8")) <= max_bytes:
        return value
    return {
        "truncated": True,
        "preview": raw.encode("utf-8")[: max(0, max_bytes - 64)].decode(
            "utf-8",
            errors="ignore",
        ),
    }


class ToolExecutor:
    """Find, authorize, validate, execute, persist, and normalize tool calls."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        settings: Settings,
        retrieval_service: Any | None = None,
        llm_service: Any | None = None,
        memory_service: Any | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings
        self.retrieval_service = retrieval_service
        self.llm_service = llm_service
        self.memory_service = memory_service

    async def execute(
        self,
        *,
        session: AsyncSession,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: uuid.UUID,
        user_role: UserRole,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        allowed_document_ids: list[uuid.UUID] | None = None,
        clock: datetime | None = None,
        active_tool_stack: list[str] | None = None,
        confirmed: bool = False,
        persist: bool = True,
    ) -> tuple[ToolExecution | None, ToolResultPayload]:
        started_wall = datetime.now(UTC)
        started_perf = time.perf_counter()
        stack = list(active_tool_stack or [])

        # Recursive same-tool prevention.
        if tool_name in stack:
            raise ToolExecutionFailedError(
                f"Recursive invocation of tool '{tool_name}' is not allowed"
            )
        stack.append(tool_name)

        record: ToolExecution | None = None
        try:
            tool = self.registry.get(tool_name)
        except ToolNotFoundError:
            if persist:
                record = await self._persist_terminal(
                    session,
                    tool_name=tool_name,
                    tool_version="unknown",
                    status=ToolExecutionStatus.denied,
                    arguments=arguments,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    started_at=started_wall,
                    error_code="tool_not_found",
                    error_message=f"Tool '{tool_name}' is not available",
                )
                return record, ToolResultPayload(
                    success=False,
                    error_code="tool_not_found",
                    error_message=f"Tool '{tool_name}' is not available",
                    expose_to_llm=True,
                )
            raise

        if not self.registry.is_effectively_enabled(tool):
            return await self._deny(
                session,
                tool=tool,
                arguments=arguments,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                request_id=request_id,
                correlation_id=correlation_id,
                started_at=started_wall,
                persist=persist,
                error=ToolDisabledError(tool_name),
            )

        if not tool.is_allowed_for_role(user_role):
            return await self._deny(
                session,
                tool=tool,
                arguments=arguments,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                request_id=request_id,
                correlation_id=correlation_id,
                started_at=started_wall,
                persist=persist,
                error=ToolPermissionDeniedError(tool_name),
            )

        if self.registry.effective_confirmation_required(tool) and not confirmed:
            return await self._deny(
                session,
                tool=tool,
                arguments=arguments,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                request_id=request_id,
                correlation_id=correlation_id,
                started_at=started_wall,
                persist=persist,
                error=ToolConfirmationRequiredError(tool_name),
                status=ToolExecutionStatus.denied,
            )

        try:
            validated = tool.validate_arguments(arguments)
        except ValidationError as exc:
            message = "; ".join(
                f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg')}"
                for err in exc.errors()[:5]
            )
            error = ToolInvalidArgumentsError(message or "Tool arguments are invalid")
            return await self._deny(
                session,
                tool=tool,
                arguments=arguments,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                request_id=request_id,
                correlation_id=correlation_id,
                started_at=started_wall,
                persist=persist,
                error=error,
                status=ToolExecutionStatus.failed,
            )

        if persist:
            record = ToolExecution(
                id=uuid.uuid4(),
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                tool_name=tool.name,
                tool_version=tool.version,
                status=ToolExecutionStatus.running,
                arguments_json=truncate_json(
                    redact_mapping(arguments),
                    max_bytes=self.settings.agent_max_result_bytes,
                ),
                started_at=started_wall,
                provider_request_id=request_id,
                correlation_id=correlation_id,
            )
            session.add(record)
            await session.flush()

        context = ToolExecutionContext(
            session=session,
            user_id=user_id,
            user_role=user_role,
            request_id=request_id,
            correlation_id=correlation_id,
            conversation_id=conversation_id,
            message_id=message_id,
            allowed_document_ids=allowed_document_ids,
            clock=clock,
            retrieval_service=self.retrieval_service,
            llm_service=self.llm_service,
            settings=self.settings,
            active_tool_stack=stack,
            extras={"memory_service": self.memory_service} if self.memory_service else {},
        )

        timeout = min(
            self.registry.effective_timeout(tool),
            self.settings.agent_tool_timeout_seconds,
        )
        try:
            result = await asyncio.wait_for(
                tool.execute(validated, context),
                timeout=timeout,
            )
        except TimeoutError:
            duration_ms = round((time.perf_counter() - started_perf) * 1000, 2)
            logger.warning(
                "tool_timeout tool=%s user_id=%s conversation_id=%s duration_ms=%s "
                "request_id=%s",
                tool.name,
                user_id,
                conversation_id,
                duration_ms,
                request_id or "-",
            )
            if record is not None:
                record.status = ToolExecutionStatus.timed_out
                record.error_code = "execution_timeout"
                record.error_message = f"Tool '{tool.name}' timed out"
                record.completed_at = datetime.now(UTC)
                record.duration_ms = duration_ms
                await session.flush()
            payload = ToolResultPayload(
                success=False,
                error_code="execution_timeout",
                error_message=f"Tool '{tool.name}' timed out",
                expose_to_llm=True,
            )
            return record, payload
        except ToolError as exc:
            duration_ms = round((time.perf_counter() - started_perf) * 1000, 2)
            logger.info(
                "tool_failed tool=%s code=%s user_id=%s conversation_id=%s "
                "duration_ms=%s request_id=%s",
                tool.name,
                exc.code,
                user_id,
                conversation_id,
                duration_ms,
                request_id or "-",
            )
            if record is not None:
                record.status = ToolExecutionStatus.failed
                record.error_code = exc.code
                record.error_message = exc.message
                record.completed_at = datetime.now(UTC)
                record.duration_ms = duration_ms
                await session.flush()
            return record, ToolResultPayload(
                success=False,
                error_code=exc.code,
                error_message=exc.message,
                expose_to_llm=True,
            )
        except Exception:
            duration_ms = round((time.perf_counter() - started_perf) * 1000, 2)
            logger.exception(
                "tool_unexpected_error tool=%s user_id=%s conversation_id=%s " "request_id=%s",
                tool.name,
                user_id,
                conversation_id,
                request_id or "-",
            )
            if record is not None:
                record.status = ToolExecutionStatus.failed
                record.error_code = "execution_failed"
                record.error_message = "Tool execution failed"
                record.completed_at = datetime.now(UTC)
                record.duration_ms = duration_ms
                await session.flush()
            return record, ToolResultPayload(
                success=False,
                error_code="execution_failed",
                error_message="Tool execution failed",
                expose_to_llm=True,
            )

        duration_ms = round((time.perf_counter() - started_perf) * 1000, 2)
        safe_data = redact_mapping(result.data)
        encoded = json.dumps(safe_data, default=str, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > self.settings.agent_max_result_bytes:
            if record is not None:
                record.status = ToolExecutionStatus.failed
                record.error_code = "result_too_large"
                record.error_message = "Tool result exceeded the configured size limit"
                record.completed_at = datetime.now(UTC)
                record.duration_ms = duration_ms
                await session.flush()
            return record, ToolResultPayload(
                success=False,
                error_code="result_too_large",
                error_message="Tool result exceeded the configured size limit",
                expose_to_llm=True,
            )

        if record is not None:
            record.status = (
                ToolExecutionStatus.succeeded if result.success else ToolExecutionStatus.failed
            )
            record.result_json = truncate_json(
                safe_data,
                max_bytes=self.settings.agent_max_result_bytes,
            )
            record.error_code = result.error_code
            record.error_message = result.error_message
            record.completed_at = datetime.now(UTC)
            record.duration_ms = duration_ms
            await session.flush()

        logger.info(
            "tool_completed tool=%s status=%s user_id=%s conversation_id=%s "
            "execution_id=%s duration_ms=%s request_id=%s",
            tool.name,
            "succeeded" if result.success else "failed",
            user_id,
            conversation_id,
            record.id if record else "-",
            duration_ms,
            request_id or "-",
        )
        return record, ToolResultPayload(
            success=result.success,
            data=safe_data if isinstance(safe_data, dict) else {"value": safe_data},
            error_code=result.error_code,
            error_message=result.error_message,
            expose_to_llm=result.expose_to_llm and tool.expose_result_to_llm,
        )

    async def _deny(
        self,
        session: AsyncSession,
        *,
        tool: BaseTool,
        arguments: dict[str, Any],
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        request_id: str | None,
        correlation_id: str | None,
        started_at: datetime,
        persist: bool,
        error: ToolError,
        status: ToolExecutionStatus = ToolExecutionStatus.denied,
    ) -> tuple[ToolExecution | None, ToolResultPayload]:
        record = None
        if persist:
            record = await self._persist_terminal(
                session,
                tool_name=tool.name,
                tool_version=tool.version,
                status=status,
                arguments=arguments,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                request_id=request_id,
                correlation_id=correlation_id,
                started_at=started_at,
                error_code=error.code,
                error_message=error.message,
            )
        return record, ToolResultPayload(
            success=False,
            error_code=error.code,
            error_message=error.message,
            expose_to_llm=True,
        )

    async def _persist_terminal(
        self,
        session: AsyncSession,
        *,
        tool_name: str,
        tool_version: str,
        status: ToolExecutionStatus,
        arguments: dict[str, Any],
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        request_id: str | None,
        correlation_id: str | None,
        started_at: datetime,
        error_code: str,
        error_message: str,
    ) -> ToolExecution:
        completed = datetime.now(UTC)
        record = ToolExecution(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            tool_name=tool_name,
            tool_version=tool_version,
            status=status,
            arguments_json=truncate_json(
                redact_mapping(arguments),
                max_bytes=self.settings.agent_max_result_bytes,
            ),
            error_code=error_code,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed,
            duration_ms=round((completed - started_at).total_seconds() * 1000, 2),
            provider_request_id=request_id,
            correlation_id=correlation_id,
        )
        session.add(record)
        await session.flush()
        return record
