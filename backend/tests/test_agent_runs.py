"""Agent run/task state machine and repository tests (Phase 9.1)."""

from __future__ import annotations

import uuid

import pytest
from app.agents.exceptions import AgentOwnershipError, AgentStateTransitionError
from app.agents.repository import AgentRunRepository
from app.agents.state_machine import (
    validate_approval_transition,
    validate_run_transition,
    validate_task_transition,
)
from app.core.config import Settings
from app.models.enums import (
    AgentApprovalStatus,
    AgentExecutionMode,
    AgentRunStatus,
    AgentTaskStatus,
    UserRole,
    UserStatus,
)
from app.models.user import User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def test_run_transitions_valid() -> None:
    validate_run_transition(AgentRunStatus.pending, AgentRunStatus.planning)
    validate_run_transition(AgentRunStatus.planning, AgentRunStatus.running)
    validate_run_transition(AgentRunStatus.running, AgentRunStatus.awaiting_approval)
    validate_run_transition(AgentRunStatus.awaiting_approval, AgentRunStatus.running)
    validate_run_transition(AgentRunStatus.running, AgentRunStatus.completed)


def test_run_transitions_reject_invalid() -> None:
    with pytest.raises(AgentStateTransitionError):
        validate_run_transition(AgentRunStatus.completed, AgentRunStatus.running)
    with pytest.raises(AgentStateTransitionError):
        validate_run_transition(AgentRunStatus.pending, AgentRunStatus.completed)
    with pytest.raises(AgentStateTransitionError):
        validate_run_transition(AgentRunStatus.cancelled, AgentRunStatus.running)


def test_task_and_approval_transitions() -> None:
    validate_task_transition(AgentTaskStatus.pending, AgentTaskStatus.ready)
    validate_task_transition(AgentTaskStatus.ready, AgentTaskStatus.running)
    validate_task_transition(AgentTaskStatus.running, AgentTaskStatus.succeeded)
    with pytest.raises(AgentStateTransitionError):
        validate_task_transition(AgentTaskStatus.succeeded, AgentTaskStatus.running)

    validate_approval_transition(AgentApprovalStatus.pending, AgentApprovalStatus.approved)
    with pytest.raises(AgentStateTransitionError):
        validate_approval_transition(AgentApprovalStatus.approved, AgentApprovalStatus.rejected)


@pytest.mark.asyncio
async def test_migration_0011_tables_and_seed(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT version_num FROM alembic_version"))
    assert result.scalar_one() == "0011_multi_agent_orchestration"

    tables = await db_session.execute(
        text(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                'agent_definitions', 'agent_runs', 'agent_tasks',
                'agent_handoffs', 'agent_approvals', 'agent_run_events'
              )
            """
        )
    )
    names = {row[0] for row in tables.fetchall()}
    assert names == {
        "agent_definitions",
        "agent_runs",
        "agent_tasks",
        "agent_handoffs",
        "agent_approvals",
        "agent_run_events",
    }

    keys = await db_session.execute(text("SELECT key FROM agent_definitions ORDER BY key"))
    assert [row[0] for row in keys.fetchall()] == [
        "conversation",
        "coordinator",
        "knowledge",
        "memory",
        "planning",
        "safety",
        "tool",
    ]


@pytest.mark.asyncio
async def test_repository_create_transition_and_ownership(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"agent-run-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Agent Run User",
        role=UserRole.user,
        status=UserStatus.active,
    )
    other = User(
        id=uuid.uuid4(),
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Other User",
        role=UserRole.user,
        status=UserStatus.active,
    )
    db_session.add_all([user, other])
    await db_session.flush()

    repo = AgentRunRepository(settings)
    run = await repo.create_run(
        db_session,
        user=user,
        conversation_id=None,
        original_request="Review my proposal and calculate contingency",
        correlation_id="corr-test-1",
        execution_mode=AgentExecutionMode.multi_agent,
    )
    assert run.status == AgentRunStatus.pending
    assert "Review my proposal" in run.original_request_summary

    await repo.transition_run(db_session, run, AgentRunStatus.planning)
    await repo.transition_run(
        db_session,
        run,
        AgentRunStatus.running,
        safe_plan_summary="1. Retrieve docs\n2. Calculate\n3. Respond",
    )
    assert run.safe_plan_summary is not None
    assert "Retrieve" in run.safe_plan_summary

    tasks = await repo.create_tasks_from_plan(
        db_session,
        run,
        [
            {
                "assigned_agent_key": "knowledge",
                "task_type": "retrieve",
                "objective": "Retrieve authorized document context",
                "sequence": 1,
                "depth": 0,
                "dependencies_json": [],
                "allowed_tools_json": ["knowledge_search"],
            },
            {
                "assigned_agent_key": "conversation",
                "task_type": "synthesize",
                "objective": "Prepare final answer",
                "sequence": 2,
                "depth": 1,
                "dependencies_json": [1],
                "allowed_tools_json": [],
            },
        ],
    )
    assert len(tasks) == 2
    await repo.transition_task(db_session, tasks[0], AgentTaskStatus.ready)
    await repo.transition_task(db_session, tasks[0], AgentTaskStatus.running)
    await repo.transition_task(
        db_session,
        tasks[0],
        AgentTaskStatus.succeeded,
        result_summary="Retrieved 2 passages",
    )

    event = await repo.add_event(
        db_session,
        run=run,
        event_type="agent_task_completed",
        agent_key="knowledge",
        task_id=tasks[0].id,
        safe_metadata={"sequence": 1},
    )
    assert event.event_type == "agent_task_completed"

    await repo.add_handoff(
        db_session,
        run=run,
        from_agent_key="knowledge",
        to_agent_key="conversation",
        reason="Document context ready",
        task_id=tasks[1].id,
    )

    owned = await repo.get_owned(db_session, user, run.id, with_details=True)
    assert owned is not None
    assert len(owned.tasks) == 2
    assert len(owned.events) == 1
    assert len(owned.handoffs) == 1

    with pytest.raises(AgentOwnershipError):
        await repo.get_owned_or_raise(db_session, other, run.id)

    await repo.transition_run(db_session, run, AgentRunStatus.completed)
    # Idempotent terminal completion
    await repo.transition_run(db_session, run, AgentRunStatus.completed)
    assert run.status == AgentRunStatus.completed

    with pytest.raises(AgentStateTransitionError):
        await repo.transition_run(db_session, run, AgentRunStatus.running)


@pytest.mark.asyncio
async def test_repository_cancel_queued_tasks(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"cancel-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Cancel User",
        role=UserRole.user,
        status=UserStatus.active,
    )
    db_session.add(user)
    await db_session.flush()

    repo = AgentRunRepository(settings)
    run = await repo.create_run(
        db_session,
        user=user,
        conversation_id=None,
        original_request="Complex multi-step request",
        correlation_id="corr-cancel",
        execution_mode=AgentExecutionMode.multi_agent,
    )
    await repo.transition_run(db_session, run, AgentRunStatus.running)
    tasks = await repo.create_tasks_from_plan(
        db_session,
        run,
        [
            {
                "assigned_agent_key": "knowledge",
                "task_type": "retrieve",
                "objective": "Retrieve",
                "sequence": 1,
            },
            {
                "assigned_agent_key": "tool",
                "task_type": "calculate",
                "objective": "Calculate",
                "sequence": 2,
            },
        ],
    )
    await repo.transition_task(db_session, tasks[0], AgentTaskStatus.running)
    cancelled = await repo.cancel_queued_tasks(db_session, run)
    assert cancelled == 2
    await repo.transition_run(db_session, run, AgentRunStatus.cancelled)
    assert run.status == AgentRunStatus.cancelled
    # Idempotent cancel
    await repo.transition_run(db_session, run, AgentRunStatus.cancelled)


@pytest.mark.asyncio
async def test_approval_create_and_resolve(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"approve-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Approve User",
        role=UserRole.user,
        status=UserStatus.active,
    )
    db_session.add(user)
    await db_session.flush()

    repo = AgentRunRepository(settings)
    run = await repo.create_run(
        db_session,
        user=user,
        conversation_id=None,
        original_request="Remember this decision",
        correlation_id="corr-approve",
        execution_mode=AgentExecutionMode.multi_agent,
    )
    await repo.transition_run(db_session, run, AgentRunStatus.running)
    tasks = await repo.create_tasks_from_plan(
        db_session,
        run,
        [
            {
                "assigned_agent_key": "memory",
                "task_type": "remember",
                "objective": "Save decision memory",
                "sequence": 1,
                "requires_approval": True,
            }
        ],
    )
    await repo.transition_task(db_session, tasks[0], AgentTaskStatus.ready)
    await repo.transition_task(db_session, tasks[0], AgentTaskStatus.awaiting_approval)
    await repo.transition_run(db_session, run, AgentRunStatus.awaiting_approval)

    approval = await repo.create_approval(
        db_session,
        run=run,
        task=tasks[0],
        user=user,
        action_type="memory_create",
        safe_action_summary="Save decision memory",
    )
    assert approval.status == AgentApprovalStatus.pending

    resolved = await repo.resolve_approval(
        db_session,
        approval,
        AgentApprovalStatus.approved,
        resolution_note="User confirmed",
    )
    assert resolved.status == AgentApprovalStatus.approved
    # Idempotent re-approve
    again = await repo.resolve_approval(
        db_session,
        approval,
        AgentApprovalStatus.approved,
    )
    assert again.status == AgentApprovalStatus.approved

    with pytest.raises(AgentStateTransitionError):
        await repo.resolve_approval(
            db_session,
            approval,
            AgentApprovalStatus.rejected,
        )


def test_context_envelope_budgets() -> None:
    from app.agents.context import AgentContextEnvelope, AgentContextLimits

    envelope = AgentContextEnvelope(
        user_request="x" * 5000,
        conversation_summary="y" * 3000,
        selected_history=[{"role": "user", "content": "h" * 2000} for _ in range(20)],
        memory_context=[{"content": "m" * 1000} for _ in range(10)],
        document_context=[{"content": "d" * 1000} for _ in range(10)],
        prior_task_results=[{"result_summary": "r" * 1000} for _ in range(10)],
        correlation_id="c1",
        limits=AgentContextLimits(
            max_characters=5000,
            max_history_messages=3,
            max_memory_items=2,
            max_document_passages=2,
            max_prior_task_results=2,
        ),
    )
    trimmed = envelope.enforce_budgets()
    assert len(trimmed.selected_history) <= 3
    assert len(trimmed.memory_context) <= 2
    assert len(trimmed.document_context) <= 2
    assert trimmed.character_count() <= 5000 + 500  # small tolerance for metadata
