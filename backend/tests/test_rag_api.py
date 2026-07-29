"""RAG query API tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.document_helpers import sample_txt_bytes
from tests.fakes.llm import FakeLLMProvider

STRONG_PASSWORD = "StrongDemoPassword123!"


async def _register(client: AsyncClient, *, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": STRONG_PASSWORD,
            "full_name": "RAG User",
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


@pytest.mark.asyncio
async def test_rag_grounded_answer_with_citations(
    rag_client: AsyncClient,
    rag_app: FastAPI,
) -> None:
    token = await _register(rag_client, email="rag-grounded@example.com")
    await _upload_ready(rag_client, token)
    llm: FakeLLMProvider = rag_app.state.fake_llm_provider
    llm.generate_calls = 0

    response = await rag_client.post(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is Cortexa?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grounded"] is True
    assert body["retrieval_count"] >= 1
    assert "[1]" in body["answer"]
    assert body["citations"]
    assert body["citations"][0]["citation_id"] == "[1]"
    assert body["citations"][0]["filename"]
    assert body["citations"][0]["excerpt"]
    assert llm.generate_calls == 1


@pytest.mark.asyncio
async def test_rag_no_context_skips_llm(
    rag_client: AsyncClient,
    rag_app: FastAPI,
) -> None:
    token = await _register(rag_client, email="rag-empty@example.com")
    llm: FakeLLMProvider = rag_app.state.fake_llm_provider
    llm.generate_calls = 0

    response = await rag_client.post(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is Cortexa?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grounded"] is False
    assert body["retrieval_count"] == 0
    assert body["citations"] == []
    assert "could not find enough information" in body["answer"].lower()
    assert llm.generate_calls == 0


@pytest.mark.asyncio
async def test_rag_user_isolation(rag_client: AsyncClient) -> None:
    token_a = await _register(rag_client, email="rag-iso-a@example.com")
    token_b = await _register(rag_client, email="rag-iso-b@example.com")
    await _upload_ready(rag_client, token_a)

    response = await rag_client.post(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"question": "What is Cortexa?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["retrieval_count"] == 0


@pytest.mark.asyncio
async def test_rag_top_k_and_foreign_document_id(
    rag_client: AsyncClient,
) -> None:
    token_a = await _register(rag_client, email="rag-topk-a@example.com")
    token_b = await _register(rag_client, email="rag-topk-b@example.com")
    doc_a = await _upload_ready(rag_client, token_a, name="a.txt")

    # Foreign document id must not leak; treated as not found for caller B.
    foreign = await rag_client.post(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"question": "What is Cortexa?", "document_ids": [doc_a]},
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "document_not_found"

    # Owner can filter by own document id and request top_k.
    ok = await rag_client.post(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"question": "What is Cortexa?", "document_ids": [doc_a], "top_k": 1},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["retrieval_count"] <= 1
    assert ok.json()["grounded"] is True


@pytest.mark.asyncio
async def test_rag_requires_auth(rag_client: AsyncClient) -> None:
    response = await rag_client.post(
        "/api/v1/rag/query",
        json={"question": "What is Cortexa?"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rag_rejects_blank_question(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="rag-blank@example.com")
    response = await rag_client.post(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rag_unknown_document_id(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="rag-missing-doc@example.com")
    response = await rag_client.post(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "What is Cortexa?",
            "document_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 404
