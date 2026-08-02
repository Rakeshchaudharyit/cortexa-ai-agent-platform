"""Persistence helpers for multi-agent runs, tasks, approvals, and events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.exceptions import AgentOwnershipError, AgentStateTransitionError
from app.agents.state_machine import (
    is_terminal_run,
    is_terminal_task,
    validate_approval_transition,
    validate_run_transition,
    validate_task_transition,
)
from app.core.config import Settings
from app.models.agent import (
    AgentApproval,
    AgentDefinition,
    AgentHandoff,
    AgentRun,
    AgentRunEvent,
    AgentTask,
)
from app.models.enums import (
    AgentApprovalStatus,
    AgentExecutionMode,
    AgentRunStatus,
    AgentTaskStatus,
)
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _safe_summary(text: str, limit: int = 500) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


class AgentRunRepository:
    """Owned agent-run persistence with explicit state transitions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_run(
        self,
        session: AsyncSession,
        *,
        user: User,
        conversation_id: uuid.UUID | None,
        original_request: str,
        correlation_id: str,
        execution_mode: AgentExecutionMode = AgentExecutionMode.single_agent,
        maximum_steps: int | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=uuid.uuid4(),
            user_id=user.id,
            conversation_id=conversation_id,
            coordinator_agent_key="coordinator",
            status=AgentRunStatus.pending,
            execution_mode=execution_mode,
            original_request_summary=_safe_summary(original_request, 500),
            maximum_steps=maximum_steps or self.settings.agent_max_steps,
            correlation_id=correlation_id,
        )
        session.add(run)
        await session.flush()
        return run

    async def get_by_correlation(
        self,
        session: AsyncSession,
        *,
        user: User,
        conversation_id: uuid.UUID | None,
        correlation_id: str,
    ) -> AgentRun | None:
        """Return an existing owned run for chat request idempotency."""
        stmt = select(AgentRun).where(
            AgentRun.user_id == user.id,
            AgentRun.conversation_id == conversation_id,
            AgentRun.correlation_id == correlation_id,
        )
        result = await session.scalar(stmt)
        return result if isinstance(result, AgentRun) else None

    async def get_owned(
        self,
        session: AsyncSession,
        user: User,
        run_id: uuid.UUID,
        *,
        with_details: bool = False,
        for_update: bool = False,
    ) -> AgentRun | None:
        stmt = select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
        if with_details:
            stmt = stmt.options(
                selectinload(AgentRun.tasks),
                selectinload(AgentRun.events),
                selectinload(AgentRun.approvals),
                selectinload(AgentRun.handoffs),
            )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.scalar(stmt)
        return result if isinstance(result, AgentRun) else None

    async def get_owned_or_raise(
        self,
        session: AsyncSession,
        user: User,
        run_id: uuid.UUID,
        *,
        with_details: bool = False,
    ) -> AgentRun:
        run = await self.get_owned(session, user, run_id, with_details=with_details)
        if run is None:
            raise AgentOwnershipError()
        return run

    async def get_by_id(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        *,
        with_details: bool = False,
    ) -> AgentRun | None:
        """Admin/internal lookup without ownership filter."""
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        if with_details:
            stmt = stmt.options(
                selectinload(AgentRun.tasks),
                selectinload(AgentRun.events),
                selectinload(AgentRun.approvals),
                selectinload(AgentRun.handoffs),
            )
        result = await session.scalar(stmt)
        return result if isinstance(result, AgentRun) else None

    async def list_owned(
        self,
        session: AsyncSession,
        user: User,
        *,
        status: AgentRunStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AgentRun], int]:
        filters = [AgentRun.user_id == user.id]
        if status is not None:
            filters.append(AgentRun.status == status)
        where = and_(*filters)
        total = await session.scalar(select(func.count()).select_from(AgentRun).where(where)) or 0
        rows = await session.scalars(
            select(AgentRun)
            .where(where)
            .options(selectinload(AgentRun.tasks))
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total)

    async def list_all(
        self,
        session: AsyncSession,
        *,
        status: AgentRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentRun], int]:
        stmt = select(AgentRun)
        count_stmt = select(func.count()).select_from(AgentRun)
        if status is not None:
            stmt = stmt.where(AgentRun.status == status)
            count_stmt = count_stmt.where(AgentRun.status == status)
        total = await session.scalar(count_stmt) or 0
        rows = await session.scalars(
            stmt.options(selectinload(AgentRun.tasks))
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total)

    async def transition_run(
        self,
        session: AsyncSession,
        run: AgentRun,
        target: AgentRunStatus,
        *,
        error_code: str | None = None,
        safe_error_message: str | None = None,
        safe_plan_summary: str | None = None,
    ) -> AgentRun:
        if run.status == target and is_terminal_run(target):
            return run  # idempotent terminal
        validate_run_transition(run.status, target)
        now = _utcnow()
        if target == AgentRunStatus.planning and run.started_at is None:
            run.started_at = now
        if target == AgentRunStatus.running and run.started_at is None:
            run.started_at = now
        if target == AgentRunStatus.completed:
            run.completed_at = now
            run.duration_ms = self._duration_ms(run, now)
        elif target == AgentRunStatus.failed:
            run.failed_at = now
            run.duration_ms = self._duration_ms(run, now)
            run.error_code = error_code
            run.safe_error_message = (
                _safe_summary(safe_error_message, 500) if safe_error_message else None
            )
        elif target == AgentRunStatus.cancelled:
            run.cancelled_at = now
            run.duration_ms = self._duration_ms(run, now)
        elif target == AgentRunStatus.timed_out:
            run.failed_at = now
            run.duration_ms = self._duration_ms(run, now)
            run.error_code = error_code or "agent_timed_out"
            run.safe_error_message = safe_error_message or "Agent run timed out"
        if safe_plan_summary is not None:
            run.safe_plan_summary = _safe_summary(safe_plan_summary, 2000)
        run.status = target
        await session.flush()
        return run

    def _duration_ms(self, run: AgentRun, now: datetime) -> int | None:
        start = run.started_at or run.created_at
        if start is None:
            return None
        return max(0, int((now - start).total_seconds() * 1000))

    async def create_tasks_from_plan(
        self,
        session: AsyncSession,
        run: AgentRun,
        tasks: list[dict[str, Any]],
    ) -> list[AgentTask]:
        created: list[AgentTask] = []
        for item in tasks:
            deps = item.get("dependencies_json") or []
            tools = item.get("allowed_tools_json") or []
            retries = item.get("maximum_retries")
            task = AgentTask(
                id=uuid.uuid4(),
                agent_run_id=run.id,
                assigned_agent_key=str(item["assigned_agent_key"]),
                task_type=str(item["task_type"]),
                objective=_safe_summary(str(item["objective"]), 1000),
                safe_input_summary=_safe_summary(str(item.get("safe_input_summary") or ""), 500),
                status=AgentTaskStatus.pending,
                sequence=int(item["sequence"]),
                depth=int(item.get("depth") or 0),
                dependencies_json=list(deps) if isinstance(deps, list) else [],
                allowed_tools_json=list(tools) if isinstance(tools, list) else [],
                requires_approval=bool(item.get("requires_approval") or False),
                maximum_retries=(
                    int(retries) if retries is not None else self.settings.agent_max_retries
                ),
            )
            session.add(task)
            created.append(task)
        await session.flush()
        return created

    async def transition_task(
        self,
        session: AsyncSession,
        task: AgentTask,
        target: AgentTaskStatus,
        *,
        result_summary: str | None = None,
        error_code: str | None = None,
        safe_error_message: str | None = None,
        increment_retry: bool = False,
    ) -> AgentTask:
        if task.status == target and is_terminal_task(target):
            return task
        validate_task_transition(task.status, target)
        now = _utcnow()
        if target == AgentTaskStatus.running and task.started_at is None:
            task.started_at = now
        if target in {
            AgentTaskStatus.succeeded,
            AgentTaskStatus.failed,
            AgentTaskStatus.skipped,
            AgentTaskStatus.cancelled,
            AgentTaskStatus.timed_out,
        }:
            task.completed_at = now
            if target == AgentTaskStatus.cancelled:
                task.cancelled_at = now
            start = task.started_at or task.created_at
            if start is not None:
                task.duration_ms = max(0, int((now - start).total_seconds() * 1000))
        if result_summary is not None:
            task.result_summary = _safe_summary(result_summary, 2000)
        if error_code is not None:
            task.error_code = error_code
        if safe_error_message is not None:
            task.safe_error_message = _safe_summary(safe_error_message, 500)
        if increment_retry:
            task.retry_count += 1
        task.status = target
        await session.flush()
        return task

    async def add_event(
        self,
        session: AsyncSession,
        *,
        run: AgentRun,
        event_type: str,
        agent_key: str | None = None,
        task_id: uuid.UUID | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> AgentRunEvent:
        event = AgentRunEvent(
            id=uuid.uuid4(),
            agent_run_id=run.id,
            task_id=task_id,
            event_type=event_type,
            agent_key=agent_key,
            safe_metadata_json=safe_metadata,
        )
        session.add(event)
        await session.flush()
        return event

    async def add_handoff(
        self,
        session: AsyncSession,
        *,
        run: AgentRun,
        from_agent_key: str,
        to_agent_key: str,
        reason: str,
        task_id: uuid.UUID | None = None,
        safe_context_summary: str = "",
    ) -> AgentHandoff:
        handoff = AgentHandoff(
            id=uuid.uuid4(),
            agent_run_id=run.id,
            task_id=task_id,
            from_agent_key=from_agent_key,
            to_agent_key=to_agent_key,
            reason=_safe_summary(reason, 500),
            safe_context_summary=_safe_summary(safe_context_summary, 1000),
        )
        session.add(handoff)
        await session.flush()
        return handoff

    async def create_approval(
        self,
        session: AsyncSession,
        *,
        run: AgentRun,
        task: AgentTask,
        user: User,
        action_type: str,
        safe_action_summary: str,
        expires_at: datetime | None = None,
    ) -> AgentApproval:
        approval = AgentApproval(
            id=uuid.uuid4(),
            agent_run_id=run.id,
            task_id=task.id,
            user_id=user.id,
            action_type=action_type,
            status=AgentApprovalStatus.pending,
            safe_action_summary=_safe_summary(safe_action_summary, 500),
            expires_at=expires_at,
        )
        session.add(approval)
        await session.flush()
        return approval

    async def get_owned_approval(
        self,
        session: AsyncSession,
        user: User,
        approval_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> AgentApproval | None:
        stmt = select(AgentApproval).where(
            AgentApproval.id == approval_id,
            AgentApproval.user_id == user.id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.scalar(stmt)
        return result if isinstance(result, AgentApproval) else None

    async def list_owned_approvals(
        self,
        session: AsyncSession,
        user: User,
        *,
        status: AgentApprovalStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AgentApproval], int]:
        filters = [AgentApproval.user_id == user.id]
        if status is not None:
            filters.append(AgentApproval.status == status)
        where = and_(*filters)
        total = (
            await session.scalar(select(func.count()).select_from(AgentApproval).where(where)) or 0
        )
        rows = await session.scalars(
            select(AgentApproval)
            .where(where)
            .order_by(AgentApproval.requested_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total)

    async def list_tasks(
        self,
        session: AsyncSession,
        run: AgentRun,
        *,
        status: AgentTaskStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentTask], int]:
        stmt = select(AgentTask).where(AgentTask.agent_run_id == run.id)
        count_stmt = (
            select(func.count()).select_from(AgentTask).where(AgentTask.agent_run_id == run.id)
        )
        if status is not None:
            stmt = stmt.where(AgentTask.status == status)
            count_stmt = count_stmt.where(AgentTask.status == status)
        total = int(await session.scalar(count_stmt) or 0)
        rows = await session.scalars(
            stmt.order_by(AgentTask.sequence.asc()).limit(limit).offset(offset)
        )
        return list(rows), total

    async def list_events(
        self,
        session: AsyncSession,
        run: AgentRun,
        *,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AgentRunEvent], int]:
        stmt = select(AgentRunEvent).where(AgentRunEvent.agent_run_id == run.id)
        count_stmt = (
            select(func.count())
            .select_from(AgentRunEvent)
            .where(AgentRunEvent.agent_run_id == run.id)
        )
        if event_type:
            stmt = stmt.where(AgentRunEvent.event_type == event_type)
            count_stmt = count_stmt.where(AgentRunEvent.event_type == event_type)
        total = int(await session.scalar(count_stmt) or 0)
        rows = await session.scalars(
            stmt.order_by(AgentRunEvent.created_at.asc(), AgentRunEvent.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total

    async def resolve_approval(
        self,
        session: AsyncSession,
        approval: AgentApproval,
        target: AgentApprovalStatus,
        *,
        resolution_note: str | None = None,
    ) -> AgentApproval:
        if approval.status == target and approval.status != AgentApprovalStatus.pending:
            return approval  # idempotent
        if approval.status != AgentApprovalStatus.pending and target != approval.status:
            raise AgentStateTransitionError(f"Approval already resolved as {approval.status.value}")
        validate_approval_transition(approval.status, target)
        now = _utcnow()
        if (
            approval.expires_at is not None
            and approval.expires_at <= now
            and target in {AgentApprovalStatus.approved, AgentApprovalStatus.rejected}
        ):
            approval.status = AgentApprovalStatus.expired
            approval.resolved_at = now
            await session.flush()
            raise AgentStateTransitionError("Approval has expired")
        approval.status = target
        approval.resolved_at = now
        if resolution_note:
            approval.resolution_note = _safe_summary(resolution_note, 500)
        await session.flush()
        return approval

    async def list_definitions(
        self,
        session: AsyncSession,
        *,
        enabled_only: bool = False,
    ) -> list[AgentDefinition]:
        stmt = select(AgentDefinition).order_by(AgentDefinition.key.asc())
        if enabled_only:
            stmt = stmt.where(AgentDefinition.enabled.is_(True))
        rows = await session.scalars(stmt)
        return list(rows)

    async def get_definition_by_key(
        self,
        session: AsyncSession,
        key: str,
    ) -> AgentDefinition | None:
        result = await session.scalar(select(AgentDefinition).where(AgentDefinition.key == key))
        return result if isinstance(result, AgentDefinition) else None

    async def cancel_queued_tasks(
        self,
        session: AsyncSession,
        run: AgentRun,
    ) -> int:
        cancelled = 0
        tasks = await session.scalars(select(AgentTask).where(AgentTask.agent_run_id == run.id))
        for task in tasks:
            if task.status in {
                AgentTaskStatus.pending,
                AgentTaskStatus.ready,
                AgentTaskStatus.running,
                AgentTaskStatus.awaiting_approval,
            }:
                await self.transition_task(session, task, AgentTaskStatus.cancelled)
                cancelled += 1
        return cancelled

    async def recover_stale_runs(self, session: AsyncSession) -> int:
        """Fail interrupted active runs; approval waits and terminals survive restart."""
        if not self.settings.agent_stale_run_recovery_enabled:
            return 0
        cutoff = _utcnow() - timedelta(seconds=self.settings.agent_stale_run_after_seconds)
        rows = await session.scalars(
            select(AgentRun).where(
                AgentRun.status.in_(
                    [
                        AgentRunStatus.pending,
                        AgentRunStatus.planning,
                        AgentRunStatus.running,
                    ]
                ),
                AgentRun.updated_at < cutoff,
            )
        )
        recovered = 0
        for run in rows:
            await self.cancel_queued_tasks(session, run)
            await self.transition_run(
                session,
                run,
                AgentRunStatus.failed,
                error_code="agent_run_interrupted",
                safe_error_message="Agent run was interrupted before completion",
            )
            await self.add_event(
                session,
                run=run,
                event_type="run_failed",
                agent_key="coordinator",
                safe_metadata={
                    "error_code": "agent_run_interrupted",
                    "recovery_policy": "fail_interrupted",
                },
            )
            recovered += 1
        return recovered
