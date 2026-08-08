"""Regression contracts for the Phase 9.9.x stabilization release."""

from __future__ import annotations

import inspect

from app.agents.coordinator import CoordinatorEngine
from app.services.chat import ChatService


def test_sse_callback_does_not_commit_coordinator_session() -> None:
    """SSE delivery must not commit while provider work owns ORM state."""
    source = inspect.getsource(ChatService._stream_into_assistant)
    callback = source.split("async def on_agent_event", 1)[1].split(
        "execution_task = asyncio.create_task", 1
    )[0]
    assert "await session.commit()" not in callback
    assert "agent_sse_event" in callback


def test_coordinator_uses_explicit_durable_checkpoints() -> None:
    source = inspect.getsource(CoordinatorEngine._execute_multi_agent)
    assert "coordinator_start_checkpoint" in source
    assert "coordinator_plan_checkpoint" in source
    assert "Checkpoint only between tasks" in source


def test_task_execution_snapshots_orm_scalars_before_provider_await() -> None:
    source = inspect.getsource(CoordinatorEngine._run_task_with_retries)
    assert "task_id = task.id" in source
    assert "agent_key = task.assigned_agent_key" in source
    assert "await session.refresh(task)" in source
    assert "MissingGreenlet" in source
