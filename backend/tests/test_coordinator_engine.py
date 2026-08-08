"""Phase 9.2 coordinator engine tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from app.agents.budgets import RunBudget
from app.agents.coordinator import CoordinatorEngine, CoordinatorRequest
from app.agents.definitions import create_default_agent_registry
from app.agents.exceptions import AgentLimitExceededError, AgentTimeoutError
from app.agents.repository import AgentRunRepository
from app.agents.schemas import AgentTaskResult
from app.core.config import Settings
from app.models.agent import AgentHandoff, AgentRun, AgentRunEvent, AgentTask
from app.models.enums import AgentRunStatus, AgentTaskStatus, UserRole, UserStatus
from app.models.user import User
from app.services.llm import LLMService
from app.tools.builtins import create_builtin_registry
from app.tools.executor import ToolExecutor
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.llm import FakeLLMProvider


def _user(email: str = "coord@example.com") -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="x",
        full_name="Coord User",
        role=UserRole.user,
        status=UserStatus.active,
        is_email_verified=True,
        created_at=now,
        updated_at=now,
    )


def _engine(settings: Settings, llm: FakeLLMProvider | None = None) -> CoordinatorEngine:
    registry = create_default_agent_registry()
    repo = AgentRunRepository(settings)
    provider = llm or FakeLLMProvider(
        generate_content="Synthesized recommendation based on retrieved facts."
    )
    llm_service = LLMService(settings=settings, provider=provider)
    tool_registry = create_builtin_registry()
    tool_executor = ToolExecutor(registry=tool_registry, settings=settings)
    return CoordinatorEngine(
        settings=settings,
        registry=registry,
        repository=repo,
        llm_service=llm_service,
        tool_executor=tool_executor,
        tool_registry=tool_registry,
    )


@pytest.mark.asyncio
async def test_single_agent_fallback_without_agent_run(
    settings: Settings, db_session: AsyncSession
) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    engine = _engine(settings)
    before = await db_session.scalar(select(func.count()).select_from(AgentRun)) or 0
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message="Explain FastAPI in two sentences.",
            correlation_id="c-single",
            enabled_tool_names=frozenset({"calculator"}),
        ),
    )
    after = await db_session.scalar(select(func.count()).select_from(AgentRun)) or 0
    assert result.used_single_agent_fallback is True
    assert result.execution_mode == "single_agent"
    assert result.run is None
    assert after == before


@pytest.mark.asyncio
async def test_multi_agent_creates_run_plan_tasks_events_handoffs(
    settings: Settings, db_session: AsyncSession
) -> None:
    user = _user("coord-multi@example.com")
    db_session.add(user)
    await db_session.flush()
    doc_id = uuid.uuid4()
    engine = _engine(settings)
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[doc_id],
            correlation_id="c-multi",
            enabled_tool_names=frozenset({"calculator", "current_datetime"}),
            document_context=[
                {
                    "document_id": str(doc_id),
                    "title": "Contract",
                    "content": "Payment terms include a late fee clause.",
                }
            ],
        ),
    )
    assert result.used_single_agent_fallback is False
    assert result.run is not None
    assert result.run.status == AgentRunStatus.completed
    assert result.plan is not None
    assert result.final_content

    tasks = (
        await db_session.scalars(
            select(AgentTask)
            .where(AgentTask.agent_run_id == result.run.id)
            .order_by(AgentTask.sequence.asc())
        )
    ).all()
    assert len(tasks) >= 2
    assert tasks[-1].assigned_agent_key == "conversation"
    # Dependency order: sequences increasing and completed
    statuses = [t.status for t in tasks]
    assert AgentTaskStatus.succeeded in statuses or AgentTaskStatus.awaiting_approval in statuses

    events = (
        await db_session.scalars(
            select(AgentRunEvent)
            .where(AgentRunEvent.agent_run_id == result.run.id)
            .order_by(AgentRunEvent.created_at.asc())
        )
    ).all()
    event_types = [e.event_type for e in events]
    assert event_types[0] == "run_started"
    assert "complexity_classified" in event_types
    assert "plan_created" in event_types
    assert "safety_checked" in event_types
    assert "run_completed" in event_types
    # Stable order: started before completed
    assert event_types.index("run_started") < event_types.index("run_completed")

    handoffs = (
        await db_session.scalars(
            select(AgentHandoff).where(AgentHandoff.agent_run_id == result.run.id)
        )
    ).all()
    assert len(handoffs) >= 1


@pytest.mark.asyncio
async def test_failed_dependency_skips_child(settings: Settings, db_session: AsyncSession) -> None:
    user = _user("coord-skip@example.com")
    db_session.add(user)
    await db_session.flush()
    engine = _engine(settings)

    async def boom(*args: Any, **kwargs: Any) -> AgentTaskResult:
        return AgentTaskResult(
            success=False,
            agent_name="knowledge",
            task_type="retrieve",
            result_summary="failed",
            error_code="knowledge_forced_failure",
            safe_error_message="forced failure",
        )

    engine.knowledge.execute = boom  # type: ignore[method-assign]
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[uuid.uuid4()],
            correlation_id="c-skip",
            enabled_tool_names=frozenset({"calculator"}),
        ),
    )
    assert result.run is not None
    tasks = (
        await db_session.scalars(
            select(AgentTask)
            .where(AgentTask.agent_run_id == result.run.id)
            .order_by(AgentTask.sequence.asc())
        )
    ).all()
    assert any(t.status == AgentTaskStatus.failed for t in tasks)
    assert any(t.status == AgentTaskStatus.skipped for t in tasks)


@pytest.mark.asyncio
async def test_budget_exceeded_fails_safely(settings: Settings, db_session: AsyncSession) -> None:
    user = _user("coord-budget@example.com")
    db_session.add(user)
    await db_session.flush()
    # Extremely small step budget
    settings.__dict__["agent_max_steps"] = 1
    engine = _engine(settings)
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[uuid.uuid4()],
            correlation_id="c-budget",
            enabled_tool_names=frozenset({"calculator"}),
            document_context=[{"title": "Doc", "content": "Clause A"}],
        ),
    )
    assert result.run is not None
    assert result.run.status in {AgentRunStatus.failed, AgentRunStatus.timed_out}
    assert result.error_code in {
        "agent_steps_exceeded",
        "agent_llm_budget_exceeded",
        "agent_tool_budget_exceeded",
        "agent_limit_exceeded",
        "agent_internal_error",
    } or (result.error_code or "").startswith("agent_")


def test_run_budget_helpers(settings: Settings) -> None:
    budget = RunBudget(
        maximum_steps=2,
        max_llm_calls=1,
        max_tool_calls=1,
        max_context_characters=100,
        run_timeout_seconds=30,
    )
    budget.consume_step()
    budget.consume_llm(1)
    with pytest.raises(AgentLimitExceededError):
        budget.require_llm(1)
    with pytest.raises(AgentLimitExceededError):
        budget.observe_context(500)


def test_run_budget_timeout() -> None:
    budget = RunBudget(
        maximum_steps=5,
        max_llm_calls=5,
        max_tool_calls=5,
        max_context_characters=1000,
        run_timeout_seconds=0,
    )
    budget.started_monotonic -= 1
    with pytest.raises(AgentTimeoutError):
        budget.check_run_timeout()


@pytest.mark.asyncio
async def test_retryable_provider_failure_retries_once(
    settings: Settings, db_session: AsyncSession
) -> None:
    user = _user("coord-retry@example.com")
    db_session.add(user)
    await db_session.flush()
    engine = _engine(settings)
    calls = {"n": 0}

    async def flaky(*args: Any, **kwargs: Any) -> AgentTaskResult:
        calls["n"] += 1
        if calls["n"] == 1:
            return AgentTaskResult(
                success=False,
                agent_name="knowledge",
                task_type="retrieve",
                result_summary="temp fail",
                error_code="knowledge_retrieval_failed",
                safe_error_message="temp",
                output={"retryable": True},
            )
        return AgentTaskResult(
            success=True,
            agent_name="knowledge",
            task_type="retrieve",
            result_summary="ok",
            output={"facts": ["A"], "citations": []},
        )

    engine.knowledge.execute = flaky  # type: ignore[method-assign]
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[uuid.uuid4()],
            correlation_id="c-retry",
            enabled_tool_names=frozenset({"calculator"}),
            document_context=[{"title": "Doc", "content": "Clause"}],
        ),
    )
    assert calls["n"] >= 2
    assert result.run is not None
    knowledge_tasks = (
        await db_session.scalars(
            select(AgentTask).where(
                AgentTask.agent_run_id == result.run.id,
                AgentTask.assigned_agent_key == "knowledge",
            )
        )
    ).all()
    assert knowledge_tasks
    assert knowledge_tasks[0].retry_count >= 1


@pytest.mark.asyncio
async def test_non_retryable_policy_error_not_retried(
    settings: Settings, db_session: AsyncSession
) -> None:
    user = _user("coord-noretry@example.com")
    db_session.add(user)
    await db_session.flush()
    engine = _engine(settings)
    calls = {"n": 0}

    async def policy_fail(*args: Any, **kwargs: Any) -> AgentTaskResult:
        calls["n"] += 1
        return AgentTaskResult(
            success=False,
            agent_name="tool",
            task_type="compute",
            result_summary="invalid",
            error_code="tool_invalid_arguments",
            safe_error_message="bad args",
            output={"retryable": False},
        )

    engine.tool.execute = policy_fail  # type: ignore[method-assign]
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[uuid.uuid4()],
            correlation_id="c-noretry",
            enabled_tool_names=frozenset({"calculator"}),
            document_context=[{"title": "Doc", "content": "Clause"}],
        ),
    )
    assert calls["n"] == 1
    assert result.run is not None


@pytest.mark.asyncio
async def test_completed_task_not_duplicated(settings: Settings, db_session: AsyncSession) -> None:
    user = _user("coord-dedupe@example.com")
    db_session.add(user)
    await db_session.flush()
    engine = _engine(settings)
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[uuid.uuid4()],
            correlation_id="c-dedupe",
            enabled_tool_names=frozenset({"calculator"}),
            document_context=[{"title": "Doc", "content": "Clause"}],
        ),
    )
    assert result.run is not None
    tasks = (
        await db_session.scalars(select(AgentTask).where(AgentTask.agent_run_id == result.run.id))
    ).all()
    sequences = [t.sequence for t in tasks]
    assert len(sequences) == len(set(sequences))


@pytest.mark.asyncio
async def test_task_timeout_works(settings: Settings, db_session: AsyncSession) -> None:
    user = _user("coord-timeout@example.com")
    db_session.add(user)
    await db_session.flush()
    settings.__dict__["agent_task_timeout_seconds"] = 0.01
    engine = _engine(settings)

    async def slow(*args: Any, **kwargs: Any) -> AgentTaskResult:
        import asyncio

        await asyncio.sleep(0.05)
        return AgentTaskResult(
            success=True,
            agent_name="knowledge",
            task_type="retrieve",
            result_summary="late",
        )

    engine.knowledge.execute = slow  # type: ignore[method-assign]
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[uuid.uuid4()],
            correlation_id="c-timeout",
            enabled_tool_names=frozenset({"calculator"}),
            document_context=[{"title": "Doc", "content": "Clause"}],
        ),
    )
    assert result.run is not None
    tasks = (
        await db_session.scalars(select(AgentTask).where(AgentTask.agent_run_id == result.run.id))
    ).all()
    assert any(t.status == AgentTaskStatus.timed_out for t in tasks) or any(
        t.status == AgentTaskStatus.skipped for t in tasks
    )


@pytest.mark.asyncio
async def test_conversation_timeout_uses_deterministic_fallback(
    settings: Settings, db_session: AsyncSession
) -> None:
    user = _user("coord-conversation-timeout@example.com")
    db_session.add(user)
    await db_session.flush()
    settings.__dict__["agent_task_timeout_seconds"] = 0.01
    engine = _engine(settings)

    async def slow_conversation(*args: Any, **kwargs: Any) -> AgentTaskResult:
        import asyncio

        await asyncio.sleep(0.05)
        return AgentTaskResult(
            success=True,
            agent_name="conversation",
            task_type="synthesize",
            result_summary="late",
            output={"content": "late"},
        )

    engine.conversation.execute = slow_conversation  # type: ignore[method-assign]
    result = await engine.execute(
        db_session,
        CoordinatorRequest(
            user=user,
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=[uuid.uuid4()],
            correlation_id="c-conversation-timeout",
            enabled_tool_names=frozenset({"calculator"}),
            document_context=[
                {
                    "title": "Contract",
                    "content": "The contract lists operational risks but no numeric budget.",
                }
            ],
        ),
    )

    assert result.run is not None
    assert result.run.status == AgentRunStatus.completed
    assert result.final_content
    assert "numeric baseline budget" in result.final_content
    tasks = (
        await db_session.scalars(select(AgentTask).where(AgentTask.agent_run_id == result.run.id))
    ).all()
    conversation_task = next(t for t in tasks if t.assigned_agent_key == "conversation")
    assert conversation_task.status == AgentTaskStatus.succeeded
    events, _ = await engine.repository.list_events(db_session, result.run)
    assert any(
        event.event_type == "task_completed"
        and (event.safe_metadata_json or {}).get("degraded_synthesis") is True
        for event in events
    )


@pytest.mark.asyncio
async def test_multi_agent_service_feature_gate(
    settings: Settings, db_session: AsyncSession
) -> None:
    from app.agents.multi_agent import MultiAgentService

    user = _user("coord-gate@example.com")
    db_session.add(user)
    await db_session.flush()
    settings.__dict__["multi_agent_enabled"] = False
    service = MultiAgentService(
        settings=settings,
        registry=create_default_agent_registry(),
        repository=AgentRunRepository(settings),
        llm_service=LLMService(settings=settings, provider=FakeLLMProvider()),
    )
    result = await service.execute(
        db_session,
        user=user,
        user_message=(
            "Review the selected contract, identify risks, calculate a 15 percent "
            "contingency, and prepare a recommendation."
        ),
        conversation_mode="document",
        selected_document_ids=[uuid.uuid4()],
        enabled_tool_names=frozenset({"calculator"}),
    )
    assert result.used_single_agent_fallback is True
