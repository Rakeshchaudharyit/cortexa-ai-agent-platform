"""Safe Phase 9.3 serialization and lifecycle operations."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.exceptions import AgentStateTransitionError
from app.agents.repository import AgentRunRepository
from app.agents.schemas import (
    AgentApprovalSummary,
    AgentRunDetailResponse,
    AgentRunEventSummary,
    AgentRunSummary,
    AgentTaskSummary,
)
from app.agents.state_machine import is_terminal_run
from app.core.exceptions import AppError
from app.models.agent import AgentApproval, AgentRun, AgentRunEvent, AgentTask
from app.models.enums import AgentApprovalStatus, AgentRunStatus, AgentTaskStatus
from app.models.user import User

_PUBLIC_METADATA_KEYS = frozenset(
    {
        "action_type",
        "allowed",
        "approval_id",
        "attempt",
        "blocked",
        "cancelled_by",
        "confidence",
        "context_characters",
        "duration_ms",
        "error_code",
        "execution_mode",
        "final_response_agent",
        "from",
        "llm_calls_used",
        "reason",
        "reason_codes",
        "recovery_policy",
        "requires_approval",
        "resolution",
        "resumed_after_approval",
        "retryable",
        "sequence",
        "steps_used",
        "task_count",
        "to",
        "tool_calls_used",
    }
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def safe_metadata(value: object, *, depth: int = 0) -> object:
    """Allow bounded scalar metadata and discard content-bearing fields."""
    if depth > 3:
        return None
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, list):
        return [safe_metadata(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, dict):
        clean: dict[str, object] = {}
        for raw_key, item in list(value.items())[:64]:
            key = str(raw_key)[:64]
            if key not in _PUBLIC_METADATA_KEYS:
                continue
            clean[key] = safe_metadata(item, depth=depth + 1)
        return clean
    return str(value)[:200]


def run_summary(run: AgentRun, *, task_count: int | None = None) -> AgentRunSummary:
    return AgentRunSummary(
        id=str(run.id),
        status=run.status.value,
        execution_mode=run.execution_mode.value,
        original_request_summary="[private user request]",
        safe_plan_summary="Multi-agent execution plan" if run.safe_plan_summary else None,
        started_at=_iso(run.started_at),
        completed_at=_iso(run.completed_at),
        duration_ms=run.duration_ms,
        steps_used=run.steps_used,
        llm_calls_used=run.llm_calls_used,
        tool_calls_used=run.tool_calls_used,
        task_count=task_count if task_count is not None else len(getattr(run, "tasks", [])),
        correlation_id=run.correlation_id,
        error_code=run.error_code,
        safe_error_message=run.safe_error_message,
        created_at=_iso(run.created_at) or "",
    )


def task_summary(task: AgentTask) -> AgentTaskSummary:
    return AgentTaskSummary(
        id=str(task.id),
        assigned_agent_key=task.assigned_agent_key,
        task_type=task.task_type,
        objective=f"{task.assigned_agent_key} agent task",
        status=task.status.value,
        sequence=task.sequence,
        depth=task.depth,
        requires_approval=task.requires_approval,
        result_summary=(f"Task {task.status.value}" if task.result_summary else None),
        error_code=task.error_code,
        safe_error_message=task.safe_error_message,
        retry_count=task.retry_count,
        duration_ms=task.duration_ms,
    )


def approval_summary(approval: AgentApproval) -> AgentApprovalSummary:
    return AgentApprovalSummary(
        id=str(approval.id),
        agent_run_id=str(approval.agent_run_id),
        task_id=str(approval.task_id),
        action_type=approval.action_type,
        status=approval.status.value,
        safe_action_summary=f"Confirm {approval.action_type.replace('_', ' ')} action",
        requested_at=_iso(approval.requested_at) or "",
        expires_at=_iso(approval.expires_at),
        resolved_at=_iso(approval.resolved_at),
        resolution_note=approval.resolution_note,
    )


def event_summary(event: AgentRunEvent) -> AgentRunEventSummary:
    metadata = safe_metadata(event.safe_metadata_json)
    return AgentRunEventSummary(
        id=str(event.id),
        event_type=event.event_type,
        agent_key=event.agent_key,
        task_id=str(event.task_id) if event.task_id else None,
        safe_metadata=metadata if isinstance(metadata, dict) else None,
        created_at=_iso(event.created_at) or "",
    )


def run_detail(run: AgentRun) -> AgentRunDetailResponse:
    base = run_summary(run, task_count=len(run.tasks)).model_dump()
    return AgentRunDetailResponse(
        **base,
        conversation_id=str(run.conversation_id) if run.conversation_id else None,
        tasks=[task_summary(item) for item in run.tasks],
        approvals=[approval_summary(item) for item in run.approvals],
        events=[event_summary(item) for item in run.events],
    )


def not_found() -> AppError:
    return AppError(code="not_found", message="Resource not found", status_code=404)


async def resolve_approval(
    session: AsyncSession,
    repository: AgentRunRepository,
    *,
    user: User,
    approval_id: uuid.UUID,
    target: AgentApprovalStatus,
    resolution_note: str | None,
    apply_approved_action: Callable[[AgentApproval, AgentRun, AgentTask | None], Awaitable[None]]
    | None = None,
    resume_after_approval: Callable[[AgentRun], Awaitable[None]] | None = None,
) -> AgentApproval:
    approval = await repository.get_owned_approval(session, user, approval_id, for_update=True)
    if approval is None:
        raise not_found()
    run = await repository.get_owned(session, user, approval.agent_run_id, with_details=True)
    if run is None:
        raise not_found()
    if is_terminal_run(run.status):
        if approval.status == target:
            return approval
        raise AppError(
            code="agent_run_terminal",
            message="Agent run is already terminal",
            status_code=409,
        )
    try:
        await repository.resolve_approval(
            session, approval, target, resolution_note=resolution_note
        )
    except AgentStateTransitionError as exc:
        if approval.status == AgentApprovalStatus.expired:
            task = next((item for item in run.tasks if item.id == approval.task_id), None)
            if task is not None and task.status == AgentTaskStatus.awaiting_approval:
                await repository.transition_task(session, task, AgentTaskStatus.timed_out)
            if run.status == AgentRunStatus.awaiting_approval:
                await repository.transition_run(
                    session,
                    run,
                    AgentRunStatus.timed_out,
                    error_code="agent_approval_expired",
                    safe_error_message="Required approval expired",
                )
                await repository.add_event(
                    session,
                    run=run,
                    event_type="run_timed_out",
                    agent_key="coordinator",
                    safe_metadata={"error_code": "agent_approval_expired"},
                )
        await session.commit()
        raise AppError(code="agent_approval_conflict", message=str(exc), status_code=409) from exc

    task = next((item for item in run.tasks if item.id == approval.task_id), None)
    if target == AgentApprovalStatus.approved:
        if apply_approved_action is None:
            await session.rollback()
            raise AppError(
                code="agent_approval_resume_unavailable",
                message="Approved action cannot be resumed safely",
                status_code=409,
            )
        try:
            await apply_approved_action(approval, run, task)
        except AppError:
            await session.rollback()
            raise
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            raise AppError(
                code="agent_approval_action_failed",
                message="Approved action could not be completed",
                status_code=409,
            ) from exc
    if task is not None and task.status == AgentTaskStatus.awaiting_approval:
        if target == AgentApprovalStatus.approved:
            await repository.transition_task(
                session, task, AgentTaskStatus.succeeded, result_summary="Approved by user"
            )
        else:
            await repository.transition_task(
                session,
                task,
                AgentTaskStatus.skipped,
                result_summary="Persistent action rejected by user",
            )
    await repository.add_event(
        session,
        run=run,
        event_type="approval_resolved",
        agent_key=task.assigned_agent_key if task else None,
        task_id=task.id if task else None,
        safe_metadata={"approval_id": str(approval.id), "resolution": target.value},
    )
    pending_approvals = [
        item
        for item in run.approvals
        if item.id != approval.id and item.status == AgentApprovalStatus.pending
    ]
    if not pending_approvals and run.status == AgentRunStatus.awaiting_approval:
        await repository.transition_run(session, run, AgentRunStatus.running)
        if target == AgentApprovalStatus.approved:
            if resume_after_approval is None:
                await session.rollback()
                raise AppError(
                    code="agent_approval_resume_unavailable",
                    message="Approved run cannot be resumed safely",
                    status_code=409,
                )
            try:
                await resume_after_approval(run)
            except AppError:
                await session.rollback()
                raise
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                raise AppError(
                    code="agent_approval_resume_failed",
                    message="Approved run could not be resumed",
                    status_code=409,
                ) from exc
        else:
            for item in run.tasks:
                if item.status in {AgentTaskStatus.pending, AgentTaskStatus.ready}:
                    await repository.transition_task(
                        session,
                        item,
                        AgentTaskStatus.skipped,
                        result_summary="Skipped because the required action was rejected",
                    )
            await repository.transition_run(session, run, AgentRunStatus.completed)
            await repository.add_event(
                session,
                run=run,
                event_type="run_completed",
                agent_key="coordinator",
                safe_metadata={"resumed_after_approval": False},
            )
    await session.commit()
    return approval
