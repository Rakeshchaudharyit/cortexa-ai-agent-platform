"""Phase 9.3 ownership, lifecycle, privacy, recovery, and admin API tests."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.api import safe_metadata
from app.agents.repository import AgentRunRepository
from app.db.session import get_session_factory
from app.models.agent import AgentDefinition, AgentRun
from app.models.conversation import Message
from app.models.enums import (
    AgentApprovalStatus,
    AgentExecutionMode,
    AgentRunStatus,
    AgentTaskStatus,
    MessageRole,
    UserRole,
)
from app.models.memory import UserMemory
from app.models.user import User

from tests.document_helpers import sample_txt_bytes


async def _register(client: AsyncClient, prefix: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{prefix}-{uuid.uuid4().hex[:8]}@example.com",
            "password": "StrongDemoPassword123!",
            "confirm_password": "StrongDemoPassword123!",
            "full_name": "Agent API User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(payload: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {payload['access_token']}"}


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
        elif not line and data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
            event_name = "message"
            data_lines = []
    if data_lines:
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


async def _create_run(
    session: AsyncSession,
    repository: AgentRunRepository,
    user: User,
    *,
    status: AgentRunStatus = AgentRunStatus.running,
) -> tuple[AgentRun, object]:
    run = await repository.create_run(
        session,
        user=user,
        conversation_id=None,
        original_request="private prompt body that must never reach admin APIs",
        correlation_id=str(uuid.uuid4()),
        execution_mode=AgentExecutionMode.multi_agent,
    )
    await repository.transition_run(session, run, status)
    tasks = await repository.create_tasks_from_plan(
        session,
        run,
        [
            {
                "assigned_agent_key": "memory",
                "task_type": "remember",
                "objective": "private memory content that must not reach agent APIs",
                "safe_input_summary": "approved preference payload",
                "sequence": 1,
                "requires_approval": True,
            }
        ],
    )
    await session.commit()
    return run, tasks[0]


def test_safe_event_metadata_removes_private_content() -> None:
    value = safe_metadata(
        {
            "sequence": 1,
            "prompt": "secret full prompt",
            "document_passage": "private passage",
            "memory_content": "private memory",
            "summary": "content hidden even under an innocent-looking key",
            "provider_payload": {"token": "secret"},
            "nested": {"status": "ok", "traceback": "private stack"},
        }
    )
    assert value == {"sequence": 1}


@pytest.mark.asyncio
async def test_complex_sse_order_complete_once_metadata_and_idempotency(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, "complex-sse")
    headers = _headers(payload)
    conversation = await chat_client.post("/api/v1/conversations", json={}, headers=headers)
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]
    uploaded = await chat_client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("phase9.txt", sample_txt_bytes(), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    client_request_id = str(uuid.uuid4())
    request_body = {
        "content": (
            "Review the selected contract, identify risks, calculate a 15 percent "
            "contingency, and prepare a recommendation."
        ),
        "document_ids": [document_id],
        "client_request_id": client_request_id,
    }

    response = await asyncio.wait_for(
        chat_client.post(
            f"/api/v1/conversations/{conversation_id}/messages/stream",
            headers=headers,
            json=request_body,
        ),
        timeout=5,
    )
    assert response.status_code == 200, response.text
    events = _parse_sse(response.text)
    names = [name for name, _data in events]
    assert names.count("complete") == 1
    assert "assistant_token" not in names
    for expected in (
        "run_started",
        "complexity_classified",
        "planning_started",
        "plan_created",
        "safety_checked",
        "task_started",
        "run_completed",
        "delta",
        "metadata",
        "complete",
    ):
        assert expected in names
    assert names.index("run_started") < names.index("planning_started")
    assert names.index("planning_started") < names.index("plan_created")
    assert names.index("run_completed") < names.index("delta")
    assert names.index("delta") < names.index("metadata") < names.index("complete")
    metadata = next(data for name, data in events if name == "metadata")
    complete = next(data for name, data in events if name == "complete")
    assert metadata["agent_run_id"] == complete["agent_run_id"]
    persisted = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}", headers=headers
    )
    assert persisted.status_code == 200
    assistant_messages = [
        item for item in persisted.json()["messages"] if item["role"] == "assistant"
    ]
    assert assistant_messages[-1]["agent_run_id"] == metadata["agent_run_id"]

    replay = await asyncio.wait_for(
        chat_client.post(
            f"/api/v1/conversations/{conversation_id}/messages/stream",
            headers=headers,
            json=request_body,
        ),
        timeout=5,
    )
    replay_events = _parse_sse(replay.text)
    assert [name for name, _data in replay_events].count("complete") == 1
    replay_metadata = next(data for name, data in replay_events if name == "metadata")
    assert replay_metadata["agent_run_id"] == metadata["agent_run_id"]

    user_id = uuid.UUID(payload["user"]["id"])
    run_count = int(
        await db_session.scalar(
            select(func.count()).select_from(AgentRun).where(AgentRun.user_id == user_id)
        )
        or 0
    )
    message_count = int(
        await db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == uuid.UUID(conversation_id))
        )
        or 0
    )
    assert run_count == 1
    assert message_count == 2


@pytest.mark.asyncio
async def test_simple_sse_stays_single_agent_without_run(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, "simple-sse")
    headers = _headers(payload)
    conversation = await chat_client.post("/api/v1/conversations", json={}, headers=headers)
    response = await chat_client.post(
        f"/api/v1/conversations/{conversation.json()['id']}/messages/stream",
        headers=headers,
        json={"content": "Hello there", "document_ids": []},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _data in events]
    assert names.count("complete") == 1
    assert "delta" in names
    assert "run_started" not in names
    user_id = uuid.UUID(payload["user"]["id"])
    count = int(
        await db_session.scalar(
            select(func.count()).select_from(AgentRun).where(AgentRun.user_id == user_id)
        )
        or 0
    )
    assert count == 0


@pytest.mark.asyncio
async def test_active_run_cancel_invokes_provider_hook_and_discards_blank_assistant(
    chat_client: AsyncClient,
    chat_app,
) -> None:
    payload = await _register(chat_client, "cancel-sse")
    headers = _headers(payload)
    conversation = await chat_client.post("/api/v1/conversations", json={}, headers=headers)
    conversation_id = conversation.json()["id"]
    uploaded = await chat_client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("cancel.txt", sample_txt_bytes(), "text/plain")},
    )
    document_id = uploaded.json()["id"]
    provider = chat_app.state.fake_llm_provider
    generate_calls_before = provider.generate_calls
    provider.generate_cancelled = False
    provider.stream_delay_seconds = 2.0

    async def execute_stream() -> str:
        response = await chat_client.post(
            f"/api/v1/conversations/{conversation_id}/messages/stream",
            headers=headers,
            json={
                "content": (
                    "Review the selected contract, identify risks, calculate a 15 percent "
                    "contingency, and prepare a recommendation."
                ),
                "document_ids": [document_id],
            },
        )
        return response.text

    stream_task = asyncio.create_task(execute_stream())
    factory = get_session_factory()
    try:
        run_id: uuid.UUID | None = None
        for _ in range(300):
            async with factory() as polling_session:
                run_id = await polling_session.scalar(
                    select(AgentRun.id).where(
                        AgentRun.user_id == uuid.UUID(payload["user"]["id"]),
                        AgentRun.status.in_([AgentRunStatus.planning, AgentRunStatus.running]),
                    )
                )
            if run_id is not None and provider.generate_calls > generate_calls_before:
                break
            await asyncio.sleep(0.01)
        assert run_id is not None
        cancelled = await chat_client.post(f"/api/v1/agent-runs/{run_id}/cancel", headers=headers)
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        await asyncio.wait_for(stream_task, timeout=5)
        assert provider.generate_cancelled is True
    finally:
        provider.stream_delay_seconds = 0.0
        if not stream_task.done():
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)

    async with factory() as verification_session:
        assistant_count = int(
            await verification_session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == uuid.UUID(conversation_id),
                    Message.role == MessageRole.assistant,
                )
            )
            or 0
        )
    assert assistant_count == 0


@pytest.mark.asyncio
async def test_owned_run_apis_pagination_safe_404_and_cancel(
    chat_client: AsyncClient,
    chat_app,
    db_session: AsyncSession,
) -> None:
    owner_payload = await _register(chat_client, "owner")
    foreign_payload = await _register(chat_client, "foreign")
    owner = await db_session.get(User, uuid.UUID(owner_payload["user"]["id"]))
    assert owner is not None
    repository: AgentRunRepository = chat_app.state.agent_run_repository
    run, _task = await _create_run(db_session, repository, owner)
    await repository.add_event(
        db_session,
        run=run,
        event_type="task_started",
        agent_key="memory",
        safe_metadata={"sequence": 1, "summary": "private document passage"},
    )
    await db_session.commit()

    listed = await chat_client.get(
        "/api/v1/agent-runs?limit=1&offset=0", headers=_headers(owner_payload)
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["task_count"] == 1
    tasks = await chat_client.get(
        f"/api/v1/agent-runs/{run.id}/tasks", headers=_headers(owner_payload)
    )
    events = await chat_client.get(
        f"/api/v1/agent-runs/{run.id}/events", headers=_headers(owner_payload)
    )
    assert tasks.status_code == events.status_code == 200
    assert tasks.json()["items"][0]["objective"] == "memory agent task"
    assert "private document passage" not in str(events.json()).lower()

    foreign = await chat_client.get(
        f"/api/v1/agent-runs/{run.id}", headers=_headers(foreign_payload)
    )
    missing = await chat_client.get(
        f"/api/v1/agent-runs/{uuid.uuid4()}", headers=_headers(foreign_payload)
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == missing.json()["error"]["code"]
    foreign_cancel = await chat_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel", headers=_headers(foreign_payload)
    )
    assert foreign_cancel.status_code == 404

    cancelled = await chat_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel", headers=_headers(owner_payload)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["tasks"][0]["status"] == "cancelled"
    again = await chat_client.post(
        f"/api/v1/agent-runs/{run.id}/cancel", headers=_headers(owner_payload)
    )
    assert again.status_code == 200

    terminal, _ = await _create_run(db_session, repository, owner)
    await repository.transition_run(db_session, terminal, AgentRunStatus.completed)
    await db_session.commit()
    protected = await chat_client.post(
        f"/api/v1/agent-runs/{terminal.id}/cancel", headers=_headers(owner_payload)
    )
    assert protected.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_approval", "expected_task"),
    [
        ("approve", AgentApprovalStatus.approved, AgentTaskStatus.succeeded),
        ("reject", AgentApprovalStatus.rejected, AgentTaskStatus.skipped),
    ],
)
async def test_approval_resolution_is_owned_terminal_and_idempotent(
    action: str,
    expected_approval: AgentApprovalStatus,
    expected_task: AgentTaskStatus,
    chat_client: AsyncClient,
    chat_app,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"approval-{action}")
    user = await db_session.get(User, uuid.UUID(payload["user"]["id"]))
    assert user is not None
    repository: AgentRunRepository = chat_app.state.agent_run_repository
    run, task = await _create_run(db_session, repository, user)
    followup = (
        await repository.create_tasks_from_plan(
            db_session,
            run,
            [
                {
                    "assigned_agent_key": "conversation",
                    "task_type": "synthesize",
                    "objective": "Prepare the response after the memory decision",
                    "sequence": 2,
                    "dependencies_json": [1],
                    "maximum_retries": 0,
                }
            ],
        )
    )[0]
    await repository.transition_task(db_session, task, AgentTaskStatus.ready)
    await repository.transition_task(db_session, task, AgentTaskStatus.awaiting_approval)
    await repository.transition_run(db_session, run, AgentRunStatus.awaiting_approval)
    approval = await repository.create_approval(
        db_session,
        run=run,
        task=task,
        user=user,
        action_type="memory_remember",
        safe_action_summary="Remember approved preference",
    )
    await db_session.commit()

    listed = await chat_client.get("/api/v1/agent-approvals", headers=_headers(payload))
    detail = await chat_client.get(
        f"/api/v1/agent-approvals/{approval.id}", headers=_headers(payload)
    )
    assert listed.status_code == detail.status_code == 200
    assert listed.json()["total"] == 1

    response = await chat_client.post(
        f"/api/v1/agent-approvals/{approval.id}/{action}",
        json={"resolution_note": "confirmed"},
        headers=_headers(payload),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == expected_approval.value
    assert response.json()["safe_action_summary"] == "Confirm memory remember action"
    repeated = await chat_client.post(
        f"/api/v1/agent-approvals/{approval.id}/{action}",
        json={},
        headers=_headers(payload),
    )
    assert repeated.status_code == 200
    await db_session.refresh(run)
    await db_session.refresh(task)
    await db_session.refresh(followup)
    assert run.status == AgentRunStatus.completed
    assert task.status == expected_task
    assert followup.status == (
        AgentTaskStatus.succeeded if action == "approve" else AgentTaskStatus.skipped
    )
    memory_count = int(
        await db_session.scalar(
            select(func.count()).select_from(UserMemory).where(UserMemory.user_id == user.id)
        )
        or 0
    )
    assert memory_count == (1 if action == "approve" else 0)


@pytest.mark.asyncio
async def test_approval_concurrency_and_foreign_ownership(
    chat_client: AsyncClient,
    chat_app,
    db_session: AsyncSession,
) -> None:
    owner_payload = await _register(chat_client, "approval-race-owner")
    foreign_payload = await _register(chat_client, "approval-race-foreign")
    owner = await db_session.get(User, uuid.UUID(owner_payload["user"]["id"]))
    assert owner is not None
    repository: AgentRunRepository = chat_app.state.agent_run_repository
    run, task = await _create_run(db_session, repository, owner)
    await repository.transition_task(db_session, task, AgentTaskStatus.ready)
    await repository.transition_task(db_session, task, AgentTaskStatus.awaiting_approval)
    await repository.transition_run(db_session, run, AgentRunStatus.awaiting_approval)
    approval = await repository.create_approval(
        db_session,
        run=run,
        task=task,
        user=owner,
        action_type="memory_remember",
        safe_action_summary="Confirm memory action",
    )
    await db_session.commit()

    foreign_detail = await chat_client.get(
        f"/api/v1/agent-approvals/{approval.id}", headers=_headers(foreign_payload)
    )
    foreign_approve = await chat_client.post(
        f"/api/v1/agent-approvals/{approval.id}/approve",
        json={},
        headers=_headers(foreign_payload),
    )
    assert foreign_detail.status_code == foreign_approve.status_code == 404

    async def approve_once() -> int:
        response = await chat_client.post(
            f"/api/v1/agent-approvals/{approval.id}/approve",
            json={},
            headers=_headers(owner_payload),
        )
        return response.status_code

    assert await asyncio.gather(approve_once(), approve_once()) == [200, 200]
    memory_count = int(
        await db_session.scalar(
            select(func.count()).select_from(UserMemory).where(UserMemory.user_id == owner.id)
        )
        or 0
    )
    assert memory_count == 1


@pytest.mark.asyncio
async def test_expired_approval_times_out_run(
    chat_client: AsyncClient,
    chat_app,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, "expired")
    user = await db_session.get(User, uuid.UUID(payload["user"]["id"]))
    assert user is not None
    repository: AgentRunRepository = chat_app.state.agent_run_repository
    run, task = await _create_run(db_session, repository, user)
    await repository.transition_task(db_session, task, AgentTaskStatus.ready)
    await repository.transition_task(db_session, task, AgentTaskStatus.awaiting_approval)
    await repository.transition_run(db_session, run, AgentRunStatus.awaiting_approval)
    approval = await repository.create_approval(
        db_session,
        run=run,
        task=task,
        user=user,
        action_type="memory_remember",
        safe_action_summary="Expired action",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await db_session.commit()
    response = await chat_client.post(
        f"/api/v1/agent-approvals/{approval.id}/approve",
        json={},
        headers=_headers(payload),
    )
    assert response.status_code == 409
    await db_session.refresh(run)
    assert run.status == AgentRunStatus.timed_out


@pytest.mark.asyncio
async def test_admin_agent_safeguards_audit_and_private_run_redaction(
    chat_client: AsyncClient,
    chat_app,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, "agent-admin")
    admin = await db_session.get(User, uuid.UUID(payload["user"]["id"]))
    assert admin is not None
    admin.role = UserRole.admin
    repository: AgentRunRepository = chat_app.state.agent_run_repository
    run, _task = await _create_run(db_session, repository, admin)
    await db_session.commit()

    blocked = await chat_client.patch(
        "/api/v1/admin/agents/coordinator",
        json={"enabled": False},
        headers=_headers(payload),
    )
    assert blocked.status_code == 409
    expanded = await chat_client.patch(
        "/api/v1/admin/agents/knowledge",
        json={"allowed_tools": ["calculator"]},
        headers=_headers(payload),
    )
    assert expanded.status_code == 422
    updated = await chat_client.patch(
        "/api/v1/admin/agents/knowledge",
        json={"timeout_seconds": 20, "maximum_steps": 2},
        headers=_headers(payload),
    )
    assert updated.status_code == 200, updated.text
    detail = await chat_client.get(f"/api/v1/admin/agent-runs/{run.id}", headers=_headers(payload))
    assert detail.status_code == 200
    blob = str(detail.json()).lower()
    assert "private prompt body" not in blob
    assert "private memory content" not in blob
    assert detail.json()["original_request_summary"] == "[private user request]"


@pytest.mark.asyncio
async def test_stale_recovery_preserves_approval_and_terminal_runs(
    db_session: AsyncSession, settings
) -> None:
    user = User(
        id=uuid.uuid4(),
        email=f"recovery-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Recovery User",
        role=UserRole.user,
    )
    db_session.add(user)
    await db_session.flush()
    repository = AgentRunRepository(settings)
    stale, _ = await _create_run(db_session, repository, user)
    waiting, _ = await _create_run(db_session, repository, user)
    await repository.transition_run(db_session, waiting, AgentRunStatus.awaiting_approval)
    completed, _ = await _create_run(db_session, repository, user)
    await repository.transition_run(db_session, completed, AgentRunStatus.completed)
    old = datetime.now(UTC) - timedelta(seconds=settings.agent_stale_run_after_seconds + 1)
    stale.updated_at = old
    waiting.updated_at = old
    completed.updated_at = old
    await db_session.commit()

    assert await repository.recover_stale_runs(db_session) == 1
    await db_session.commit()
    await db_session.refresh(stale)
    await db_session.refresh(waiting)
    await db_session.refresh(completed)
    assert stale.status == AgentRunStatus.failed
    assert waiting.status == AgentRunStatus.awaiting_approval
    assert completed.status == AgentRunStatus.completed


@pytest.mark.asyncio
async def test_agent_definition_seed_remains_present(db_session: AsyncSession) -> None:
    definitions = list(await db_session.scalars(select(AgentDefinition)))
    assert {item.key for item in definitions} >= {"coordinator", "safety", "conversation"}

@pytest.mark.asyncio
async def test_conversation_detail_exposes_active_agent_run_for_refresh_recovery(
    chat_client: AsyncClient,
    chat_app: FastAPI,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, "active-run-refresh")
    headers = _headers(payload)
    conversation_response = await chat_client.post(
        "/api/v1/conversations",
        json={},
        headers=headers,
    )
    assert conversation_response.status_code == 201
    conversation_id = uuid.UUID(conversation_response.json()["id"])
    user = await db_session.get(User, uuid.UUID(payload["user"]["id"]))
    assert user is not None

    repository = AgentRunRepository(chat_app.state.settings)
    run = await repository.create_run(
        db_session,
        user=user,
        conversation_id=conversation_id,
        original_request="Remember a durable preference after confirmation",
        correlation_id=str(uuid.uuid4()),
        execution_mode=AgentExecutionMode.multi_agent,
    )
    await repository.transition_run(db_session, run, AgentRunStatus.planning)
    await repository.transition_run(db_session, run, AgentRunStatus.running)
    await repository.transition_run(db_session, run, AgentRunStatus.awaiting_approval)
    await db_session.commit()

    detail = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["active_agent_run_id"] == str(run.id)
