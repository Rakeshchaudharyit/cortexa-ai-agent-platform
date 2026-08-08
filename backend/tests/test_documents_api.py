"""Document API tests — upload, list, detail, delete, ownership, duplicates, pagination."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.document_helpers import make_pdf_bytes, sample_md_bytes, sample_txt_bytes

STRONG_PASSWORD = "StrongDemoPassword123!"


async def _register(
    client: AsyncClient,
    *,
    email: str,
    full_name: str = "Doc User",
) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
            "full_name": full_name,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


@pytest.mark.asyncio
async def test_upload_list_detail_delete(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="docs-crud@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    upload = await rag_client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("sample.txt", sample_txt_bytes(), "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["status"] == "ready"
    assert body["original_filename"] == "sample.txt"
    assert body["chunk_count"] >= 1
    assert body["processing_mode"] == "synchronous"
    document_id = body["id"]

    listed = await rag_client.get("/api/v1/documents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == document_id

    detail = await rag_client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == document_id

    deleted = await rag_client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content in (b"", b"null")

    missing = await rag_client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_upload_requires_auth(rag_client: AsyncClient) -> None:
    response = await rag_client.post(
        "/api/v1/documents",
        files={"file": ("sample.txt", sample_txt_bytes(), "text/plain")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_document_rejected(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="docs-dup@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("sample.txt", sample_txt_bytes(), "text/plain")}
    first = await rag_client.post("/api/v1/documents", headers=headers, files=files)
    assert first.status_code == 201
    second = await rag_client.post("/api/v1/documents", headers=headers, files=files)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_document"


@pytest.mark.asyncio
async def test_document_ownership_isolation(rag_client: AsyncClient) -> None:
    token_a = await _register(rag_client, email="docs-a@example.com")
    token_b = await _register(rag_client, email="docs-b@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    upload = await rag_client.post(
        "/api/v1/documents",
        headers=headers_a,
        files={"file": ("private.txt", sample_txt_bytes(), "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    listed_b = await rag_client.get("/api/v1/documents", headers=headers_b)
    assert listed_b.status_code == 200
    assert listed_b.json()["total"] == 0

    detail_b = await rag_client.get(f"/api/v1/documents/{document_id}", headers=headers_b)
    assert detail_b.status_code == 404

    delete_b = await rag_client.delete(f"/api/v1/documents/{document_id}", headers=headers_b)
    assert delete_b.status_code == 404


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="docs-badtype@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = await rag_client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("evil.exe", b"MZ binary", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_document_type"


@pytest.mark.asyncio
async def test_upload_pdf_and_md(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="docs-formats@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    pdf = await rag_client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("notes.pdf", make_pdf_bytes(), "application/pdf")},
    )
    assert pdf.status_code == 201, pdf.text
    assert pdf.json()["status"] == "ready"

    md = await rag_client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("notes.md", sample_md_bytes(), "text/markdown")},
    )
    assert md.status_code == 201, md.text


@pytest.mark.asyncio
async def test_list_pagination(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="docs-page@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    for index in range(3):
        content = f"Document number {index} with unique content for Cortexa.\n".encode()
        response = await rag_client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": (f"doc-{index}.txt", content, "text/plain")},
        )
        assert response.status_code == 201, response.text

    page = await rag_client.get(
        "/api/v1/documents",
        headers=headers,
        params={"limit": 2, "offset": 0},
    )
    assert page.status_code == 200
    payload = page.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert len(payload["items"]) == 2

    page2 = await rag_client.get(
        "/api/v1/documents",
        headers=headers,
        params={"limit": 2, "offset": 2},
    )
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 1


@pytest.mark.asyncio
async def test_embeddings_status_public(rag_client: AsyncClient, rag_app: FastAPI) -> None:
    _ = rag_app
    response = await rag_client.get("/api/v1/embeddings/status")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert body["configured_dimension"] == 768
    assert "status" in body

@pytest.mark.asyncio
async def test_document_folder_metadata_archive_restore(rag_client: AsyncClient) -> None:
    token = await _register(rag_client, email="docs-lifecycle@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    folder_response = await rag_client.post(
        "/api/v1/documents/folders",
        headers=headers,
        json={"name": "Architecture", "description": "Platform design documents"},
    )
    assert folder_response.status_code == 201, folder_response.text
    folder_id = folder_response.json()["id"]

    upload = await rag_client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("architecture.txt", sample_txt_bytes(), "text/plain")},
        data={"folder_id": folder_id},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]
    assert upload.json()["folder_id"] == folder_id

    updated = await rag_client.patch(
        f"/api/v1/documents/{document_id}",
        headers=headers,
        json={"title": "Platform Architecture", "folder_id": folder_id, "tags": ["Architecture", "Production"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Platform Architecture"
    assert updated.json()["tags"] == ["architecture", "production"]

    archived = await rag_client.post(f"/api/v1/documents/{document_id}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    active_list = await rag_client.get("/api/v1/documents", headers=headers)
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 0

    archived_list = await rag_client.get("/api/v1/documents", headers=headers, params={"archived": "true"})
    assert archived_list.status_code == 200
    assert archived_list.json()["total"] == 1

    restored = await rag_client.post(f"/api/v1/documents/{document_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False

    deleted_folder = await rag_client.delete(f"/api/v1/documents/folders/{folder_id}", headers=headers)
    assert deleted_folder.status_code == 204
    detail = await rag_client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["folder_id"] is None
