"""Safe administrator controls and visibility for registered agents."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.admin.audit import record_admin_action
from app.agents.api import approval_summary, event_summary, run_summary, task_summary
from app.agents.base import AgentRuntimeOverride
from app.agents.definitions import create_default_agent_registry
from app.agents.registry import AgentRegistry
from app.agents.repository import AgentRunRepository
from app.agents.schemas import (
    AdminAgentRunDetailResponse,
    AdminAgentRunListResponse,
    AdminAgentRunSummary,
    AdminAgentUpdateRequest,
    AgentDefinitionListResponse,
    AgentDefinitionView,
)
from app.api.deps import CurrentAdminUser, DbSessionDep
from app.core.exceptions import AppError
from app.core.logging import request_id_ctx
from app.models.agent import AgentRun
from app.models.enums import AgentRunStatus

router = APIRouter()


def _components(request: Request) -> tuple[AgentRegistry, AgentRunRepository]:
    registry = getattr(request.app.state, "agent_registry", None)
    repository = getattr(request.app.state, "agent_run_repository", None)
    if registry is None:
        registry = create_default_agent_registry()
        request.app.state.agent_registry = registry
    if not isinstance(repository, AgentRunRepository):
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            raise RuntimeError("Agent services are not configured")
        repository = AgentRunRepository(settings)
        request.app.state.agent_run_repository = repository
    return registry, repository


def _admin_run(run: AgentRun) -> AdminAgentRunSummary:
    safe = run_summary(run, task_count=len(run.tasks)).model_dump()
    # Administrators receive operational metadata, never user prompt content.
    safe["original_request_summary"] = "[private user request]"
    return AdminAgentRunSummary(
        **safe,
        user_id=str(run.user_id),
        conversation_id=str(run.conversation_id) if run.conversation_id else None,
    )


@router.get("/agents", response_model=AgentDefinitionListResponse)
async def list_agents(request: Request, _admin: CurrentAdminUser) -> AgentDefinitionListResponse:
    registry, _repository = _components(request)
    items = registry.list_views()
    return AgentDefinitionListResponse(items=items, total=len(items))


@router.get("/agents/{agent_key}", response_model=AgentDefinitionView)
async def get_agent(
    agent_key: str, request: Request, _admin: CurrentAdminUser
) -> AgentDefinitionView:
    registry, _repository = _components(request)
    try:
        return registry.to_view(registry.get(agent_key))
    except Exception as exc:
        raise AppError(code="not_found", message="Resource not found", status_code=404) from exc


@router.patch("/agents/{agent_key}", response_model=AgentDefinitionView)
async def update_agent(
    agent_key: str,
    body: AdminAgentUpdateRequest,
    request: Request,
    admin: CurrentAdminUser,
    session: DbSessionDep,
) -> AgentDefinitionView:
    registry, repository = _components(request)
    try:
        agent = registry.get(agent_key)
    except Exception as exc:
        raise AppError(code="not_found", message="Resource not found", status_code=404) from exc
    if body.enabled is False and not registry.can_disable(agent_key):
        raise AppError(
            code="required_agent",
            message="Coordinator and Safety agents cannot be disabled",
            status_code=409,
        )
    if body.allowed_tools is not None:
        requested = frozenset(body.allowed_tools)
        if not requested.issubset(agent.allowed_tools):
            raise AppError(
                code="invalid_tool_restriction",
                message="Agent tool restrictions cannot expand the server allow-list",
                status_code=422,
            )
    definition = await repository.get_definition_by_key(session, agent_key)
    if definition is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if body.enabled is not None:
        definition.enabled = body.enabled
    if body.timeout_seconds is not None:
        definition.timeout_seconds = body.timeout_seconds
    if body.maximum_steps is not None:
        definition.maximum_steps = body.maximum_steps
    if body.allowed_tools is not None:
        definition.allowed_tools_json = sorted(set(body.allowed_tools))
    current = registry.get_override(agent_key) or AgentRuntimeOverride()
    override = AgentRuntimeOverride(
        enabled=body.enabled if body.enabled is not None else current.enabled,
        timeout_seconds=(
            body.timeout_seconds if body.timeout_seconds is not None else current.timeout_seconds
        ),
        maximum_steps=(
            body.maximum_steps if body.maximum_steps is not None else current.maximum_steps
        ),
        allowed_tools=(
            frozenset(body.allowed_tools)
            if body.allowed_tools is not None
            else current.allowed_tools
        ),
    )
    overrides: dict[str, AgentRuntimeOverride] = {}
    for item in registry.list_all():
        saved = registry.get_override(item.name)
        if saved is not None:
            overrides[item.name] = saved
    overrides[agent_key] = override
    registry.apply_overrides(overrides)
    await record_admin_action(
        session,
        actor_user_id=admin.id,
        action="agent_configuration_updated",
        target_type="agent_definition",
        target_id=agent_key,
        safe_summary=f"Updated bounded configuration for agent {agent_key}",
        metadata={"changed_fields": sorted(body.model_fields_set)},
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return registry.to_view(agent)


@router.get("/agent-runs", response_model=AdminAgentRunListResponse)
async def list_runs(
    request: Request,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    status: AgentRunStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminAgentRunListResponse:
    _registry, repository = _components(request)
    rows, total = await repository.list_all(session, status=status, limit=limit, offset=offset)
    return AdminAgentRunListResponse(
        items=[_admin_run(item) for item in rows], total=total, limit=limit, offset=offset
    )


@router.get("/agent-runs/{run_id}", response_model=AdminAgentRunDetailResponse)
async def get_run(
    run_id: uuid.UUID,
    request: Request,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
) -> AdminAgentRunDetailResponse:
    _registry, repository = _components(request)
    run = await repository.get_by_id(session, run_id, with_details=True)
    if run is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return AdminAgentRunDetailResponse(
        **_admin_run(run).model_dump(),
        tasks=[task_summary(item) for item in run.tasks],
        approvals=[approval_summary(item) for item in run.approvals],
        events=[event_summary(item) for item in run.events],
    )
