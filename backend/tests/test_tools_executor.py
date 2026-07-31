"""Calculator, datetime, executor, and security tests."""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from app.core.config import Settings
from app.models.enums import ToolExecutionStatus, UserRole
from app.models.tool_execution import ToolExecution
from app.tools.base import BaseTool
from app.tools.builtins.calculator import CalculatorTool, evaluate_expression
from app.tools.builtins.current_datetime import CurrentDatetimeInput, CurrentDatetimeTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import (
    ToolExecutionFailedError,
    ToolInvalidArgumentsError,
)
from app.tools.executor import ToolExecutor, redact_mapping
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolResultPayload
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


def test_calculator_basic_arithmetic() -> None:
    assert evaluate_expression("2 + 3 * 4") == 14


def test_calculator_parentheses() -> None:
    assert evaluate_expression("(1200 * 15) / 100") == 180


def test_calculator_percent_form() -> None:
    assert evaluate_expression("(2450 * 18) / 100") == 441


def test_calculator_division_by_zero() -> None:
    with pytest.raises(ToolExecutionFailedError, match="Division by zero"):
        evaluate_expression("10 / 0")


def test_calculator_unsupported_syntax() -> None:
    with pytest.raises(ToolInvalidArgumentsError):
        evaluate_expression("import os")


def test_calculator_excessive_exponent_rejected() -> None:
    with pytest.raises(ToolInvalidArgumentsError, match="Exponent"):
        evaluate_expression("2 ** 100")


def test_calculator_no_eval_usage() -> None:
    source = inspect.getsource(evaluate_expression)
    assert "eval(" not in source
    assert "exec(" not in source
    # AST parser path must remain.
    assert "ast.parse" in inspect.getsource(
        __import__("app.tools.builtins.calculator", fromlist=["evaluate_expression"])
    )


@pytest.mark.asyncio
async def test_datetime_valid_timezone() -> None:
    tool = CurrentDatetimeTool()
    ctx = ToolExecutionContext(
        session=None,  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        user_role=UserRole.user,
        clock=datetime(2026, 7, 30, 6, 30, tzinfo=UTC),
    )
    result = await tool.execute(
        CurrentDatetimeInput(timezone="Asia/Kolkata"),
        ctx,
    )
    assert result.success
    assert result.data["timezone"] == "Asia/Kolkata"
    assert result.data["date"] == "2026-07-30"
    assert result.data["utc_offset"] == "+05:30"


@pytest.mark.asyncio
async def test_datetime_invalid_timezone() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CurrentDatetimeInput(timezone="Not/AZone")


@pytest.mark.asyncio
async def test_datetime_deterministic_clock() -> None:
    tool = CurrentDatetimeTool()
    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    ctx = ToolExecutionContext(
        session=None,  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        user_role=UserRole.user,
        clock=fixed,
    )
    result = await tool.execute(CurrentDatetimeInput(timezone="UTC"), ctx)
    assert result.data["iso"].startswith("2026-01-02T03:04:05")


def test_redact_secrets() -> None:
    payload = {"password": "secret", "expression": "1+1", "nested": {"api_key": "x"}}
    redacted = redact_mapping(payload)
    assert redacted["password"] == "[redacted]"
    assert redacted["nested"]["api_key"] == "[redacted]"
    assert redacted["expression"] == "1+1"


class _EchoInput(BaseModel):
    value: str = Field(min_length=1)


class _EchoTool(BaseTool):
    name: ClassVar[str] = "echo_tool"
    description: ClassVar[str] = "Echo"
    input_model: ClassVar[type[BaseModel]] = _EchoInput
    timeout_seconds: ClassVar[int] = 1

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        assert isinstance(arguments, _EchoInput)
        if arguments.value == "boom":
            raise RuntimeError("secret traceback should not leak")
        if arguments.value == "slow":
            import asyncio

            await asyncio.sleep(5)
        if arguments.value == "huge":
            return ToolResultPayload(success=True, data={"blob": "x" * 200_000})
        return ToolResultPayload(success=True, data={"value": arguments.value})


class _AdminOnlyTool(BaseTool):
    name: ClassVar[str] = "admin_only_tool"
    description: ClassVar[str] = "Admin"
    input_model: ClassVar[type[BaseModel]] = _EchoInput
    required_roles: ClassVar[frozenset[UserRole]] = frozenset({UserRole.admin})

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        return ToolResultPayload(success=True, data={})


class _DisabledTool(BaseTool):
    name: ClassVar[str] = "disabled_tool"
    description: ClassVar[str] = "Disabled"
    input_model: ClassVar[type[BaseModel]] = _EchoInput
    enabled: ClassVar[bool] = False

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        return ToolResultPayload(success=True, data={})


def _executor(settings: Settings) -> ToolExecutor:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    registry.register(_AdminOnlyTool())
    registry.register(_DisabledTool())
    registry.register(CalculatorTool())
    return ToolExecutor(registry=registry, settings=settings)


async def _persist_user(session: AsyncSession) -> uuid.UUID:
    from app.models.enums import UserStatus
    from app.models.user import User

    user_id = uuid.uuid4()
    session.add(
        User(
            id=user_id,
            email=f"tools-{user_id.hex[:8]}@example.com",
            full_name="Tools User",
            password_hash="not-a-real-hash",
            role=UserRole.user,
            status=UserStatus.active,
        )
    )
    await session.flush()
    return user_id


@pytest.mark.asyncio
async def test_invalid_arguments_rejected(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    settings.agent_max_result_bytes = 32_768
    user_id = await _persist_user(db_session)
    executor = _executor(settings)
    record, result = await executor.execute(
        session=db_session,
        tool_name="echo_tool",
        arguments={},
        user_id=user_id,
        user_role=UserRole.user,
    )
    assert result.success is False
    assert result.error_code == "invalid_arguments"
    assert record is not None
    assert record.status == ToolExecutionStatus.failed


@pytest.mark.asyncio
async def test_unknown_tool_rejected(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    user_id = await _persist_user(db_session)
    executor = _executor(settings)
    record, result = await executor.execute(
        session=db_session,
        tool_name="nope",
        arguments={},
        user_id=user_id,
        user_role=UserRole.user,
    )
    assert result.error_code == "tool_not_found"
    assert record is not None
    assert record.status == ToolExecutionStatus.denied


@pytest.mark.asyncio
async def test_disabled_tool_rejected(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    user_id = await _persist_user(db_session)
    executor = _executor(settings)
    _, result = await executor.execute(
        session=db_session,
        tool_name="disabled_tool",
        arguments={"value": "x"},
        user_id=user_id,
        user_role=UserRole.user,
    )
    assert result.error_code == "tool_disabled"


@pytest.mark.asyncio
async def test_unauthorized_tool_denied(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    user_id = await _persist_user(db_session)
    executor = _executor(settings)
    _, result = await executor.execute(
        session=db_session,
        tool_name="admin_only_tool",
        arguments={"value": "x"},
        user_id=user_id,
        user_role=UserRole.user,
    )
    assert result.error_code == "permission_denied"


@pytest.mark.asyncio
async def test_timeout_handled(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    settings.agent_tool_timeout_seconds = 1
    user_id = await _persist_user(db_session)
    executor = _executor(settings)
    record, result = await executor.execute(
        session=db_session,
        tool_name="echo_tool",
        arguments={"value": "slow"},
        user_id=user_id,
        user_role=UserRole.user,
    )
    assert result.error_code == "execution_timeout"
    assert record is not None
    assert record.status == ToolExecutionStatus.timed_out
    assert record.duration_ms is not None


@pytest.mark.asyncio
async def test_oversized_result_handled(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    settings.agent_max_result_bytes = 2048
    user_id = await _persist_user(db_session)
    executor = _executor(settings)
    record, result = await executor.execute(
        session=db_session,
        tool_name="echo_tool",
        arguments={"value": "huge"},
        user_id=user_id,
        user_role=UserRole.user,
    )
    assert result.error_code == "result_too_large"
    assert record is not None
    assert record.status == ToolExecutionStatus.failed


@pytest.mark.asyncio
async def test_internal_exception_sanitized(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    user_id = await _persist_user(db_session)
    executor = _executor(settings)
    _, result = await executor.execute(
        session=db_session,
        tool_name="echo_tool",
        arguments={"value": "boom"},
        user_id=user_id,
        user_role=UserRole.user,
    )
    assert result.error_code == "execution_failed"
    assert result.error_message == "Tool execution failed"
    assert "traceback" not in (result.error_message or "").lower()


@pytest.mark.asyncio
async def test_recursive_tool_calls_prevented(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    executor = _executor(settings)
    with pytest.raises(ToolExecutionFailedError, match="Recursive"):
        await executor.execute(
            session=db_session,
            tool_name="echo_tool",
            arguments={"value": "x"},
            user_id=uuid.uuid4(),
            user_role=UserRole.user,
            active_tool_stack=["echo_tool"],
            persist=False,
        )


@pytest.mark.asyncio
async def test_success_persisted_with_duration(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    user_id = await _persist_user(db_session)

    executor = _executor(settings)
    record, result = await executor.execute(
        session=db_session,
        tool_name="calculator",
        arguments={"expression": "1 + 2"},
        user_id=user_id,
        user_role=UserRole.user,
    )
    await db_session.commit()
    assert result.success
    assert record is not None
    assert record.status == ToolExecutionStatus.succeeded
    assert record.duration_ms is not None
    assert record.result_json == {"expression": "1 + 2", "result": 3}

    loaded = await db_session.get(ToolExecution, record.id)
    assert loaded is not None
    assert loaded.arguments_json == {"expression": "1 + 2"}
