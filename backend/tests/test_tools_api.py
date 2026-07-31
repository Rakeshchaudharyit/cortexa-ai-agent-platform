"""Tool API authentication, ownership, and pagination tests."""

from __future__ import annotations

import uuid

import pytest
from app.models.enums import ToolExecutionStatus, UserRole, UserStatus
from app.models.tool_execution import ToolExecution
from app.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongDemoPassword123!",
            "confirm_password": "StrongDemoPassword123!",
            "full_name": "Tools Tester",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_tool_list_requires_auth(chat_client: AsyncClient) -> None:
    response = await chat_client.get("/api/v1/tools")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tool_list_authenticated_and_role_filtered(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, f"tools-list-{uuid.uuid4().hex[:8]}@example.com")
    response = await chat_client.get(
        "/api/v1/tools",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["tools"]}
    assert names == {
        "calculator",
        "conversation_summary",
        "current_datetime",
        "knowledge_search",
    }


@pytest.mark.asyncio
async def test_execution_list_paginated_and_owned(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await _register(chat_client, f"tools-hist-{uuid.uuid4().hex[:8]}@example.com")
    me = await chat_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = uuid.UUID(me.json()["id"])

    other = User(
        id=uuid.uuid4(),
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Other",
        password_hash="not-a-real-hash",
        role=UserRole.user,
        status=UserStatus.active,
    )
    db_session.add(other)
    await db_session.flush()

    for index in range(3):
        db_session.add(
            ToolExecution(
                id=uuid.uuid4(),
                user_id=user_id,
                tool_name="calculator",
                tool_version="1.0.0",
                status=ToolExecutionStatus.succeeded,
                arguments_json={"expression": f"{index}+1"},
                result_json={"result": index + 1},
            )
        )
    foreign_id = uuid.uuid4()
    db_session.add(
        ToolExecution(
            id=foreign_id,
            user_id=other.id,
            tool_name="calculator",
            tool_version="1.0.0",
            status=ToolExecutionStatus.succeeded,
            arguments_json={"expression": "9+9"},
            result_json={"result": 18},
        )
    )
    await db_session.commit()

    response = await chat_client.get(
        "/api/v1/tool-executions?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 2
    assert all(item["tool_name"] == "calculator" for item in payload["items"])

    denied = await chat_client.get(
        f"/api/v1/tool-executions/{foreign_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 404

    own_id = payload["items"][0]["id"]
    detail = await chat_client.get(
        f"/api/v1/tool-executions/{own_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    body = detail.json()
    assert "arguments_json" in body
    assert "password" not in str(body).lower() or "[redacted]" in str(body).lower()


@pytest.mark.asyncio
async def test_anonymous_execution_requests_rejected(chat_client: AsyncClient) -> None:
    assert (await chat_client.get("/api/v1/tool-executions")).status_code == 401
    assert (await chat_client.get(f"/api/v1/tool-executions/{uuid.uuid4()}")).status_code == 401
