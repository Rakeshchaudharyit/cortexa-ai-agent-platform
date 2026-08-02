"""Owned multi-agent run and approval APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.agents.api import (
    approval_summary,
    event_summary,
    not_found,
    resolve_approval,
    run_detail,
    run_summary,
    task_summary,
)
from app.agents.definitions import create_default_agent_registry
from app.agents.repository import AgentRunRepository
from app.agents.schemas import (
    AgentApprovalListResponse,
    AgentApprovalResolutionRequest,
    AgentApprovalSummary,
    AgentDefinitionListResponse,
    AgentEventListResponse,
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentTaskListResponse,
)
from app.agents.state_machine import is_terminal_run
from app.api.deps import CurrentActiveUser, DbSessionDep
from app.core.exceptions import AppError
from app.models.agent import AgentApproval, AgentRun, AgentTask
from app.models.enums import AgentApprovalStatus, AgentRunStatus, AgentTaskStatus

router = APIRouter(tags=["agents"])


def _repository(request: Request) -> AgentRunRepository:
    repository = getattr(request.app.state, "agent_run_repository", None)
    if not isinstance(repository, AgentRunRepository):
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            raise RuntimeError("Agent run repository is not configured")
        repository = AgentRunRepository(settings)
        request.app.state.agent_run_repository = repository
    return repository


@router.get("/agents", response_model=AgentDefinitionListResponse)
async def list_agents(
    request: Request,
    _user: CurrentActiveUser,
    enabled_only: Annotated[bool, Query()] = True,
) -> AgentDefinitionListResponse:
    registry = getattr(request.app.state, "agent_registry", None)
    if registry is None:
        registry = create_default_agent_registry()
        request.app.state.agent_registry = registry
    items = registry.list_views(enabled_only=enabled_only)
    return AgentDefinitionListResponse(items=items, total=len(items))


@router.get("/agent-runs", response_model=AgentRunListResponse)
async def list_runs(
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
    status: AgentRunStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentRunListResponse:
    rows, total = await _repository(request).list_owned(
        session, user, status=status, limit=limit, offset=offset
    )
    return AgentRunListResponse(
        items=[run_summary(item, task_count=len(item.tasks)) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/agent-runs/{run_id}", response_model=AgentRunDetailResponse)
async def get_run(
    run_id: uuid.UUID,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
) -> AgentRunDetailResponse:
    run = await _repository(request).get_owned(session, user, run_id, with_details=True)
    if run is None:
        raise not_found()
    return run_detail(run)


@router.get("/agent-runs/{run_id}/tasks", response_model=AgentTaskListResponse)
async def list_run_tasks(
    run_id: uuid.UUID,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
    status: AgentTaskStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentTaskListResponse:
    repository = _repository(request)
    run = await repository.get_owned(session, user, run_id)
    if run is None:
        raise not_found()
    rows, total = await repository.list_tasks(
        session, run, status=status, limit=limit, offset=offset
    )
    return AgentTaskListResponse(
        items=[task_summary(item) for item in rows], total=total, limit=limit, offset=offset
    )


@router.get("/agent-runs/{run_id}/events", response_model=AgentEventListResponse)
async def list_run_events(
    run_id: uuid.UUID,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
    event_type: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentEventListResponse:
    repository = _repository(request)
    run = await repository.get_owned(session, user, run_id)
    if run is None:
        raise not_found()
    rows, total = await repository.list_events(
        session, run, event_type=event_type, limit=limit, offset=offset
    )
    return AgentEventListResponse(
        items=[event_summary(item) for item in rows], total=total, limit=limit, offset=offset
    )


@router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunDetailResponse)
async def cancel_run(
    run_id: uuid.UUID,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
) -> AgentRunDetailResponse:
    repository = _repository(request)
    # Signal in-process work before acquiring the database row lock. A provider
    # call may still own an open transaction, so waiting for the lock first can
    # prevent the cancellation hook from ever reaching that call.
    owned_run = await repository.get_owned(session, user, run_id)
    if owned_run is None:
        raise not_found()
    multi_agent = getattr(request.app.state, "multi_agent_service", None)
    if multi_agent is not None:
        multi_agent.request_cancel(owned_run.id)

    run = await repository.get_owned(session, user, run_id, with_details=True, for_update=True)
    if run is None:
        raise not_found()
    if run.status == AgentRunStatus.cancelled:
        return run_detail(run)
    if is_terminal_run(run.status):
        raise AppError(
            code="agent_run_terminal",
            message="Completed agent runs cannot be cancelled",
            status_code=409,
        )
    await repository.cancel_queued_tasks(session, run)
    await repository.transition_run(session, run, AgentRunStatus.cancelled)
    await repository.add_event(
        session,
        run=run,
        event_type="run_cancelled",
        agent_key="coordinator",
        safe_metadata={"cancelled_by": "owner"},
    )
    for approval in run.approvals:
        if approval.status == AgentApprovalStatus.pending:
            await repository.resolve_approval(session, approval, AgentApprovalStatus.cancelled)
    await session.commit()
    return run_detail(run)


@router.get("/agent-approvals", response_model=AgentApprovalListResponse)
async def list_approvals(
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
    status: AgentApprovalStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentApprovalListResponse:
    rows, total = await _repository(request).list_owned_approvals(
        session, user, status=status, limit=limit, offset=offset
    )
    return AgentApprovalListResponse(
        items=[approval_summary(item) for item in rows], total=total, limit=limit, offset=offset
    )


@router.get("/agent-approvals/{approval_id}", response_model=AgentApprovalSummary)
async def get_approval(
    approval_id: uuid.UUID,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
) -> AgentApprovalSummary:
    approval = await _repository(request).get_owned_approval(session, user, approval_id)
    if approval is None:
        raise not_found()
    return approval_summary(approval)


async def _resolve(
    approval_id: uuid.UUID,
    body: AgentApprovalResolutionRequest,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
    target: AgentApprovalStatus,
) -> AgentApprovalSummary:
    async def apply_approved_action(
        approval: AgentApproval,
        run: AgentRun,
        task: AgentTask | None,
    ) -> None:
        memory_service = getattr(request.app.state, "memory_service", None)
        if memory_service is None or not approval.action_type.startswith("memory_"):
            raise AppError(
                code="agent_approval_action_unsupported",
                message="Approved action cannot be resumed safely",
                status_code=409,
            )
        action = approval.action_type.removeprefix("memory_")
        payload = (
            task.safe_input_summary
            if task is not None and task.safe_input_summary
            else approval.safe_action_summary
        )
        if action == "forget":
            await memory_service.forget_matching(
                session,
                user,
                query=payload,
                conversation_id=run.conversation_id,
            )
            return
        if action not in {"remember", "update"}:
            raise AppError(
                code="agent_approval_action_unsupported",
                message="Approved action cannot be resumed safely",
                status_code=409,
            )
        await memory_service.remember_explicit(
            session,
            user,
            payload,
            conversation_id=run.conversation_id,
        )

    async def resume_after_approval(run: AgentRun) -> None:
        multi_agent = getattr(request.app.state, "multi_agent_service", None)
        coordinator = getattr(multi_agent, "coordinator", None)
        if coordinator is None:
            raise AppError(
                code="agent_approval_resume_unavailable",
                message="Approved run cannot be resumed safely",
                status_code=409,
            )
        await coordinator.resume_after_approval(session, user=user, run=run)

    approval = await resolve_approval(
        session,
        _repository(request),
        user=user,
        approval_id=approval_id,
        target=target,
        resolution_note=body.resolution_note,
        apply_approved_action=(
            apply_approved_action if target == AgentApprovalStatus.approved else None
        ),
        resume_after_approval=(
            resume_after_approval if target == AgentApprovalStatus.approved else None
        ),
    )
    return approval_summary(approval)


@router.post("/agent-approvals/{approval_id}/approve", response_model=AgentApprovalSummary)
async def approve(
    approval_id: uuid.UUID,
    body: AgentApprovalResolutionRequest,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
) -> AgentApprovalSummary:
    return await _resolve(approval_id, body, request, session, user, AgentApprovalStatus.approved)


@router.post("/agent-approvals/{approval_id}/reject", response_model=AgentApprovalSummary)
async def reject(
    approval_id: uuid.UUID,
    body: AgentApprovalResolutionRequest,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
) -> AgentApprovalSummary:
    return await _resolve(approval_id, body, request, session, user, AgentApprovalStatus.rejected)
