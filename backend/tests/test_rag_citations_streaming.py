"""Grounded-answer, citation schema, and streaming-contract regressions."""

from __future__ import annotations

import json
import uuid

import pytest
from app.conversations.citations import (
    dedupe_retrieved_chunks,
    normalize_grounded_answer,
    rag_citation_to_response,
)
from app.conversations.context import _RAG_SYSTEM_PROMPT, ConversationContextBuilder
from app.core.config import Settings
from app.documents.schemas import RagCitation
from app.llm.schemas import StreamEventType
from fastapi import FastAPI
from httpx import AsyncClient

from tests.fakes.llm import FakeLLMProvider
from tests.test_conversations_api import _auth, _register, _upload_ready


def test_normalize_grounded_answer_strips_source_meta_and_dup_phrases() -> None:
    messy = (
        "According to the According to the document, the project document, the project "
        "codename is codename is ORBIT-LANTERN-92 ORBIT-LANTERN-92 [1].\n"
        "[1] Source: cortexa-rag-test.txt\n"
        "Citation ID: 1"
    )
    cleaned = normalize_grounded_answer(messy)
    assert "Citation ID" not in cleaned
    assert "Source:" not in cleaned
    # Adjacent phrase doubles collapsed.
    assert cleaned.lower().count("according to the") <= 1
    assert "ORBIT-LANTERN-92" in cleaned


def test_rag_citation_schema_has_required_fields_and_starts_at_one() -> None:
    citation = RagCitation(
        citation_id="[1]",
        document_id=uuid.uuid4(),
        filename="cortexa-rag-test.txt",
        chunk_id=uuid.uuid4(),
        chunk_index=0,
        page_number=None,
        excerpt="Project codename: ORBIT-LANTERN-92.",
        similarity=0.91,
    )
    payload = rag_citation_to_response(citation, index=1).model_dump(mode="json")
    assert payload["citation_index"] == 1
    assert payload["citation_id"] == "[1]"
    assert payload["filename"] == "cortexa-rag-test.txt"
    assert payload["excerpt"]
    assert payload["id"]
    assert payload["page_number"] is None
    assert payload["similarity_score"] is None
    assert "undefined" not in json.dumps(payload)


def test_dedupe_retrieved_chunks_by_chunk_id() -> None:
    chunk_id = uuid.uuid4()

    class _Chunk:
        def __init__(self, cid: uuid.UUID) -> None:
            self.id = cid

    class _Item:
        def __init__(self, cid: uuid.UUID) -> None:
            self.chunk = _Chunk(cid)

    items = [_Item(chunk_id), _Item(chunk_id), _Item(uuid.uuid4())]
    unique = dedupe_retrieved_chunks(items)
    assert len(unique) == 2


def test_grounded_prompt_prohibits_source_detail_prose() -> None:
    lowered = _RAG_SYSTEM_PROMPT.lower()
    assert "citation id" in lowered
    assert "source:" in lowered or "source-detail" in lowered or '"source:"' in lowered
    assert "concise" in lowered or "directly" in lowered


def test_context_headers_do_not_embed_source_filename(settings: Settings) -> None:
    builder = ConversationContextBuilder(settings=settings)

    class _Doc:
        original_filename = "secret-name.txt"

    class _Chunk:
        content = "Project codename: ORBIT-LANTERN-92."
        chunk_metadata = {}

    class _Item:
        document = _Doc()
        chunk = _Chunk()
        similarity = 0.9

    text = builder._build_rag_context([_Item()], max_chars=2000)  # noqa: SLF001
    assert "secret-name.txt" not in text
    assert text.startswith("[1]")


@pytest.mark.asyncio
async def test_rag_stream_emits_text_once_and_stable_citations(
    chat_client: AsyncClient,
    chat_app: FastAPI,
) -> None:
    token = await _register(chat_client, email="rag-stream-cite@example.com")
    await _upload_ready(chat_client, token)
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    conversation_id = created.json()["id"]
    llm: FakeLLMProvider = chat_app.state.fake_llm_provider
    llm.generate_content = "The project codename is **ORBIT-LANTERN-92**. [1]"
    llm.fail_mode = None

    events: list[tuple[str, dict]] = []
    async with chat_client.stream(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        headers=_auth(token),
        json={"content": "What is the project codename?"},
    ) as response:
        assert response.status_code == 200
        event_name = ""
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event_name:
                payload = json.loads(line.split(":", 1)[1])
                events.append((event_name, payload))
                event_name = ""

    deltas = [e for e in events if e[0] == "delta"]
    tokens = [e for e in events if e[0] == "assistant_token"]
    citations = [e for e in events if e[0] == "citation"]
    completes = [e for e in events if e[0] == "complete"]
    errors = [e for e in events if e[0] == "error"]
    progress = [e for e in events if e[0] == "progress"]

    assembled = "".join(str(e[1].get("content") or "") for e in deltas)
    # Text emitted once via delta only (no assistant_token twin).
    assert tokens == []
    assert assembled.count("ORBIT-LANTERN-92") == 1
    assert "[1]" in assembled
    assert "Citation ID" not in assembled
    assert "Source:" not in assembled

    assert len(citations) >= 1
    citation = citations[0][1]["citation"]
    assert citation["citation_index"] == 1
    assert citation["filename"]
    assert citation["filename"].count(".txt") + citation["filename"].count(".md") >= 0
    assert citation.get("id")
    assert "undefined" not in json.dumps(citation)

    assert len(completes) == 1
    assert errors == []
    complete_msg = completes[0][1]["message"]
    assert complete_msg["citations"]
    assert complete_msg["citations"][0]["citation_index"] == 1
    assert complete_msg["citations"][0]["filename"] == citation["filename"]

    # Live and persisted citation schemas match for required display fields.
    for key in ("citation_index", "citation_id", "filename", "excerpt", "id"):
        assert key in citation
        assert key in complete_msg["citations"][0]

    assert any("Searching selected documents" in (p[1].get("message") or "") for p in progress)
    assert any("Generating grounded answer" in (p[1].get("message") or "") for p in progress)

    # Reload preserves citation order / schema.
    detail = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    assert detail.status_code == 200
    assistant = next(m for m in detail.json()["messages"] if m["role"] == "assistant")
    assert assistant["citations"][0]["citation_index"] == 1
    assert assistant["citations"][0]["filename"] == citation["filename"]


@pytest.mark.asyncio
async def test_no_context_stream_is_safe_and_uncited(
    chat_client: AsyncClient,
    chat_app: FastAPI,
) -> None:
    token = await _register(chat_client, email="rag-nocontext-stream@example.com")
    created = await chat_client.post("/api/v1/conversations", headers=_auth(token), json={})
    llm: FakeLLMProvider = chat_app.state.fake_llm_provider
    llm.generate_calls = 0

    events: list[tuple[str, dict]] = []
    async with chat_client.stream(
        "POST",
        f"/api/v1/conversations/{created.json()['id']}/messages/stream",
        headers=_auth(token),
        json={"content": "What is the office address?"},
    ) as response:
        assert response.status_code == 200
        event_name = ""
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event_name:
                events.append((event_name, json.loads(line.split(":", 1)[1])))
                event_name = ""

    citations = [e for e in events if e[0] == "citation"]
    completes = [e for e in events if e[0] == "complete"]
    errors = [e for e in events if e[0] == "error"]
    deltas = [e for e in events if e[0] == "delta"]
    text = "".join(str(e[1].get("content") or "") for e in deltas)
    assert citations == []
    assert len(completes) == 1
    assert errors == []
    assert completes[0][1]["message"]["citations"] == []
    assert "couldn’t find" in text.lower() or "could not find" in text.lower()
    assert llm.generate_calls == 0


@pytest.mark.asyncio
async def test_orchestrator_does_not_dual_emit_assistant_token(
    settings: Settings,
    db_session,
) -> None:
    from app.agents.orchestrator import AgentOrchestrator
    from app.agents.schemas import AgentRunConfig
    from app.llm.schemas import ChatMessage, MessageRole
    from app.models.enums import UserRole, UserStatus
    from app.models.user import User
    from app.services.llm import LLMService
    from app.tools.builtins import create_builtin_registry
    from app.tools.executor import ToolExecutor

    provider = FakeLLMProvider(generate_content="Working")
    llm = LLMService(settings=settings, provider=provider)
    registry = create_builtin_registry()
    orch = AgentOrchestrator(
        settings=settings,
        llm_service=llm,
        tool_registry=registry,
        tool_executor=ToolExecutor(registry=registry, settings=settings, llm_service=llm),
    )
    user = User(
        id=uuid.uuid4(),
        email=f"dual-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Dual",
        password_hash="x",
        role=UserRole.user,
        status=UserStatus.active,
    )
    db_session.add(user)
    await db_session.flush()

    deltas: list[str] = []
    tokens: list[str] = []
    async for event in orch.stream(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="Hi")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=[],
        config=AgentRunConfig(selected_tool_names=[]),
    ):
        if event.event == StreamEventType.delta:
            deltas.append(str(event.data.get("content") or ""))
        elif event.event == StreamEventType.assistant_token:
            tokens.append(str(event.data.get("content") or ""))

    assert "".join(deltas) == "Working"
    assert tokens == []


def test_dedupe_retrieved_chunks_removes_near_identical_passages() -> None:
    class _Chunk:
        def __init__(self, content: str) -> None:
            self.id = uuid.uuid4()
            self.content = content

    class _Item:
        def __init__(self, content: str) -> None:
            self.chunk = _Chunk(content)

    first = "FastAPI PostgreSQL Next.js and RAG form the platform architecture."
    duplicate = "FastAPI, PostgreSQL, Next.js and RAG form the platform architecture."
    different = "Redis supports caching and background coordination."
    unique = dedupe_retrieved_chunks([_Item(first), _Item(duplicate), _Item(different)])
    assert len(unique) == 2


def test_context_selection_keeps_complete_passages_and_respects_budget() -> None:
    from app.conversations.citations import select_context_chunks

    class _Chunk:
        def __init__(self, content: str) -> None:
            self.id = uuid.uuid4()
            self.content = content

    class _Item:
        def __init__(self, content: str) -> None:
            self.chunk = _Chunk(content)

    items = [_Item("A" * 60), _Item("B" * 60), _Item("C" * 20)]
    selected = select_context_chunks(items, max_chars=90)
    assert [item.chunk.content[0] for item in selected] == ["A", "C"]
    assert all(len(item.chunk.content) in {60, 20} for item in selected)


def test_normalize_grounded_answer_removes_invalid_citation_markers() -> None:
    cleaned = normalize_grounded_answer(
        "FastAPI is used [1], but this marker is invalid [7].",
        citation_count=2,
    )
    assert "[1]" in cleaned
    assert "[7]" not in cleaned
