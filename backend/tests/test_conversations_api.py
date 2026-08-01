"""Phase 5 conversation API, context, ownership, and chat tests."""

from __future__ import annotations

import json
import uuid

import pytest
from app.conversations.context import ConversationContextBuilder
from app.core.config import Settings
from app.models.conversation import Message
from app.models.enums import MessageRole, MessageStatus
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.document_helpers import sample_txt_bytes
from tests.fakes.llm import FakeLLMProvider

STRONG_PASSWORD = "StrongDemoPassword123!"


async def _register(client: AsyncClient, *, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
            "full_name": "Chat User",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


async def _upload_ready(client: AsyncClient, token: str, *, name: str = "notes.txt") -> str:
    response = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (name, sample_txt_bytes(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "ready"
    return str(payload["id"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
        elif line == "" and data_lines:
            payload = json.loads("\n".join(data_lines))
            events.append((event_name, payload))
            event_name = "message"
            data_lines = []
    if data_lines:
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


@pytest.mark.asyncio
async def test_create_list_get_conversation(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, email="conv-create@example.com")
    created = await chat_client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == "New conversation"
    assert body["title_is_auto"] is True
    assert body["status"] == "active"
    assert body["message_count"] == 0

    listed = await chat_client.get("/api/v1/conversations", headers=_auth(token))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == body["id"]

    detail = await chat_client.get(
        f"/api/v1/conversations/{body['id']}",
        headers=_auth(token),
    )
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


@pytest.mark.asyncio
async def test_new_user_empty_conversation_list_returns_200(
    chat_client: AsyncClient,
) -> None:
    token = await _register(chat_client, email="conv-empty@example.com")
    listed = await chat_client.get("/api/v1/conversations", headers=_auth(token))
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["items"] == []
    assert payload["total"] == 0
    assert "error" not in payload


@pytest.mark.asyncio
async def test_schema_errors_are_not_empty_conversation_lists(
    chat_app: FastAPI,
    db_session: object,
) -> None:
    """Missing-table / DB errors must be 500, never a forged empty 200 list."""
    _ = db_session
    from app.services.conversations import ConversationService

    async def _boom(self: object, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError('relation "conversations" does not exist')

    # Bind on the instance used by the app so the route hits the failure path.
    service: ConversationService = chat_app.state.conversation_service
    service.list_conversations = _boom.__get__(service, ConversationService)  # type: ignore[method-assign]

    transport = ASGITransport(app=chat_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register(client, email="conv-schema-err@example.com")
        response = await client.get("/api/v1/conversations", headers=_auth(token))

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "items" not in body
    assert "total" not in body


@pytest.mark.asyncio
async def test_custom_title_and_validation(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, email="conv-title@example.com")
    created = await chat_client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"title": "  Project notes  "},
    )
    assert created.status_code == 201
    assert created.json()["title"] == "Project notes"
    assert created.json()["title_is_auto"] is False

    blank = await chat_client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"title": "   "},
    )
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_foreign_conversation_safe_404(chat_client: AsyncClient) -> None:
    token_a = await _register(chat_client, email="conv-a@example.com")
    token_b = await _register(chat_client, email="conv-b@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token_a), json={})
    conversation_id = created.json()["id"]

    response = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token_b),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


@pytest.mark.asyncio
async def test_rename_archive_unarchive_delete(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, email="conv-lifecycle@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]

    renamed = await chat_client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
        json={"title": "Renamed chat"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed chat"
    assert renamed.json()["title_is_auto"] is False

    archived = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/archive",
        headers=_auth(token),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    rejected = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "hello", "document_ids": []},
    )
    assert rejected.status_code == 409

    unarchived = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/unarchive",
        headers=_auth(token),
    )
    assert unarchived.status_code == 200
    assert unarchived.json()["status"] == "active"

    deleted = await chat_client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    assert deleted.status_code == 204
    missing = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_search_by_title_and_message(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, email="conv-search@example.com")
    created = await chat_client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"title": "Alpha Planning"},
    )
    conversation_id = created.json()["id"]
    await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "UniqueZebraQuestion", "document_ids": []},
    )

    by_title = await chat_client.get(
        "/api/v1/conversations",
        headers=_auth(token),
        params={"q": "Alpha"},
    )
    assert by_title.status_code == 200
    assert by_title.json()["total"] >= 1

    by_message = await chat_client.get(
        "/api/v1/conversations",
        headers=_auth(token),
        params={"q": "UniqueZebraQuestion"},
    )
    assert by_message.status_code == 200
    assert by_message.json()["total"] >= 1


@pytest.mark.asyncio
async def test_cross_user_search_isolation(chat_client: AsyncClient) -> None:
    token_a = await _register(chat_client, email="search-a@example.com")
    token_b = await _register(chat_client, email="search-b@example.com")
    created = await chat_client.post(
        "/api/v1/conversations",
        headers=_auth(token_a),
        json={"title": "SecretTopicXYZ"},
    )
    conversation_id = created.json()["id"]
    await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token_a),
        json={"content": "SecretPayloadXYZ", "document_ids": []},
    )

    response = await chat_client.get(
        "/api/v1/conversations",
        headers=_auth(token_b),
        params={"q": "SecretTopicXYZ"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_multi_turn_general_chat_and_auto_title(
    chat_client: AsyncClient,
    chat_app: FastAPI,
) -> None:
    token = await _register(chat_client, email="chat-general@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]
    llm: FakeLLMProvider = chat_app.state.fake_llm_provider
    llm.generate_content = "General assistant reply"
    llm.generate_calls = 0

    first = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "Explain Cortexa briefly", "document_ids": []},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["assistant_message"]["content"] == "General assistant reply"
    assert body["assistant_message"]["status"] == "complete"
    assert body["conversation"]["title"] != "New conversation"
    assert body["conversation"]["title_is_auto"] is True
    assert llm.generate_calls >= 1

    llm.generate_content = "Follow-up answer using prior context"
    second = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "Say more", "document_ids": []},
    )
    assert second.status_code == 200
    detail = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    messages = detail.json()["messages"]
    assert len(messages) == 4
    assert [m["sequence_number"] for m in messages] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_manual_title_preserved(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, email="chat-manual-title@example.com")
    created = await chat_client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"title": "Keep This Title"},
    )
    conversation_id = created.json()["id"]
    response = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "Hello there", "document_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["conversation"]["title"] == "Keep This Title"
    assert response.json()["conversation"]["title_is_auto"] is False


@pytest.mark.asyncio
async def test_rag_chat_citations_and_no_context(
    chat_client: AsyncClient,
    chat_app: FastAPI,
) -> None:
    token = await _register(chat_client, email="chat-rag@example.com")
    doc_id = await _upload_ready(chat_client, token)
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]
    llm: FakeLLMProvider = chat_app.state.fake_llm_provider
    llm.generate_content = "Grounded answer with [1]"
    llm.generate_calls = 0

    grounded = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "What is Cortexa?"},
    )
    assert grounded.status_code == 200, grounded.text
    assistant = grounded.json()["assistant_message"]
    assert assistant["grounded"] is True
    assert assistant["citations"]
    assert assistant["citations"][0]["filename"]
    assert assistant["prompt_tokens"] == 3
    assert assistant["latency_ms"] is not None
    assert llm.generate_calls >= 1

    selected = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "Again?", "document_ids": [doc_id]},
    )
    assert selected.status_code == 200

    foreign = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "Again?", "document_ids": [str(uuid.uuid4())]},
    )
    assert foreign.status_code == 404

    # No-context: user with no docs
    token2 = await _register(chat_client, email="chat-nocontext@example.com")
    created2 = await chat_client.post("/api/v1/conversations", headers=_auth(token2), json={})
    llm.generate_calls = 0
    fallback = await chat_client.post(
        f"/api/v1/conversations/{created2.json()['id']}/messages",
        headers=_auth(token2),
        json={"content": "What is Cortexa?"},
    )
    assert fallback.status_code == 200
    assert fallback.json()["assistant_message"]["grounded"] is False
    assert fallback.json()["assistant_message"]["citations"] == []
    assert llm.generate_calls == 0


@pytest.mark.asyncio
async def test_streaming_chat_events(chat_client: AsyncClient, chat_app: FastAPI) -> None:
    token = await _register(chat_client, email="chat-stream@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]
    llm: FakeLLMProvider = chat_app.state.fake_llm_provider
    llm.fail_mode = None
    llm.generate_content = "Hello world"

    async with chat_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        headers=_auth(token),
        json={"content": "Stream please", "document_ids": []},
    ) as response:
        assert response.status_code == 200
        parts: list[str] = []
        async for chunk in response.aiter_text():
            parts.append(chunk)
        raw = "".join(parts)

    events = _parse_sse(raw)
    names = [name for name, _ in events]
    assert "start" in names
    assert "delta" in names
    assert "metadata" in names
    assert "complete" in names
    assert "error" not in names
    complete = next(data for name, data in events if name == "complete")
    assert complete["message"]["content"] == "Hello world"
    assert complete["message"]["status"] == "complete"


@pytest.mark.asyncio
async def test_streaming_provider_error(chat_client: AsyncClient, chat_app: FastAPI) -> None:
    token = await _register(chat_client, email="chat-stream-err@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]
    llm: FakeLLMProvider = chat_app.state.fake_llm_provider
    llm.fail_mode = "stream_error"

    async with chat_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        headers=_auth(token),
        json={"content": "Fail stream", "document_ids": []},
    ) as response:
        parts2: list[str] = []
        async for chunk in response.aiter_text():
            parts2.append(chunk)
        raw = "".join(parts2)

    events = _parse_sse(raw)
    assert any(name == "error" for name, _ in events)
    detail = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    statuses = [m["status"] for m in detail.json()["messages"] if m["role"] == "assistant"]
    assert "failed" in statuses
    llm.fail_mode = None


@pytest.mark.asyncio
async def test_edit_and_regenerate(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, email="chat-edit@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]
    first = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "Original question", "document_ids": []},
    )
    user_message_id = first.json()["user_message"]["id"]
    assistant_id = first.json()["assistant_message"]["id"]

    edited = await chat_client.patch(
        f"/api/v1/conversations/{conversation_id}/messages/{user_message_id}",
        headers=_auth(token),
        json={"content": "Edited question"},
    )
    assert edited.status_code == 200
    assert edited.json()["content"] == "Edited question"
    assert edited.json()["edited_from_message_id"] == user_message_id

    detail = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    active = detail.json()["messages"]
    assert len(active) == 1
    assert active[0]["role"] == "user"
    assert active[0]["content"] == "Edited question"

    regenerated = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/regenerate",
        headers=_auth(token),
        json={"document_ids": []},
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["assistant_message"]["id"] != assistant_id
    assert regenerated.json()["user_message"]["content"] == "Edited question"

    # Older user message edit rejected
    second = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"content": "Second question", "document_ids": []},
    )
    older_id = second.json()["user_message"]["id"]
    # After second message, editing the previous active user message should fail
    # (latest is the second one). First get latest user from detail.
    detail2 = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    users = [m for m in detail2.json()["messages"] if m["role"] == "user"]
    older = users[0]["id"]
    latest = users[-1]["id"]
    assert older != latest
    rejected = await chat_client.patch(
        f"/api/v1/conversations/{conversation_id}/messages/{older}",
        headers=_auth(token),
        json={"content": "Nope"},
    )
    assert rejected.status_code == 400
    _ = older_id


@pytest.mark.asyncio
async def test_idempotency_client_request_id(chat_client: AsyncClient) -> None:
    token = await _register(chat_client, email="chat-idem@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]
    request_id = str(uuid.uuid4())

    first = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={
            "content": "Idempotent hello",
            "document_ids": [],
            "client_request_id": request_id,
        },
    )
    assert first.status_code == 200
    second = await chat_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={
            "content": "Idempotent hello",
            "document_ids": [],
            "client_request_id": request_id,
        },
    )
    assert second.status_code == 200
    assert second.json()["user_message"]["id"] == first.json()["user_message"]["id"]
    assert second.json()["assistant_message"]["id"] == first.json()["assistant_message"]["id"]

    detail = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    assert len(detail.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_usage_summary_isolation(chat_client: AsyncClient) -> None:
    token_a = await _register(chat_client, email="usage-a@example.com")
    token_b = await _register(chat_client, email="usage-b@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token_a), json={})
    await chat_client.post(
        f"/api/v1/conversations/{created.json()['id']}/messages",
        headers=_auth(token_a),
        json={"content": "Usage probe", "document_ids": []},
    )
    await _upload_ready(chat_client, token_a)

    summary_a = await chat_client.get("/api/v1/usage/summary", headers=_auth(token_a))
    summary_b = await chat_client.get("/api/v1/usage/summary", headers=_auth(token_b))
    assert summary_a.status_code == 200
    assert summary_a.json()["conversations"] >= 1
    assert summary_a.json()["user_messages"] >= 1
    assert summary_a.json()["documents"] >= 1
    assert summary_b.json()["conversations"] == 0
    assert summary_b.json()["messages"] == 0


@pytest.mark.asyncio
async def test_anonymous_rejected(chat_client: AsyncClient) -> None:
    response = await chat_client.get("/api/v1/conversations")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_message_too_large(chat_client: AsyncClient, settings: Settings) -> None:
    token = await _register(chat_client, email="chat-large@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    oversized = "x" * (settings.message_max_characters + 1)
    response = await chat_client.post(
        f"/api/v1/conversations/{created.json()['id']}/messages",
        headers=_auth(token),
        json={"content": oversized, "document_ids": []},
    )
    assert response.status_code in {413, 422}


def test_context_builder_trimming_and_priority(settings: Settings) -> None:
    builder = ConversationContextBuilder(settings)
    history = [
        Message(
            id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=MessageRole.user,
            content=f"old-{index}-" + ("y" * 200),
            status=MessageStatus.complete,
            sequence_number=index,
            is_active=True,
        )
        for index in range(1, 20)
    ]
    failed = Message(
        id=uuid.uuid4(),
        conversation_id=history[0].conversation_id,
        user_id=history[0].user_id,
        role=MessageRole.assistant,
        content="failed answer",
        status=MessageStatus.failed,
        sequence_number=100,
        is_active=True,
    )
    built = builder.build(
        current_user_content="current question",
        history_messages=[*history, failed],
        summary="Earlier topics were discussed.",
        retrieved=[],
        general_mode=True,
    )
    assert built.messages[-1].content == "current question"
    assert all("failed answer" not in m.content for m in built.messages)
    assert built.history_message_count <= settings.conversation_max_history_messages
    assert built.trimmed is True
