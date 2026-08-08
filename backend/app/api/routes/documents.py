"""Document upload, list, detail, and delete API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status

from app.api.deps import CurrentActiveUser, DbSessionDep, DocumentServiceDep, SettingsDep
from app.documents.schemas import (
    DocumentFolderCreate,
    DocumentFolderListResponse,
    DocumentFolderResponse,
    DocumentListResponse,
    DocumentMetadataUpdate,
    DocumentResponse,
    DocumentTimelineResponse,
    DocumentVersionCompareResponse,
    DocumentVersionHistoryResponse,
)
from app.jobs.service import JobService
from app.models.enums import DocumentStatus

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document and queue background ingestion",
)
async def upload_document(
    request: Request,
    user: CurrentActiveUser,
    session: DbSessionDep,
    settings: SettingsDep,
    document_service: DocumentServiceDep,
    file: UploadFile = File(...),
    folder_id: uuid.UUID | None = Form(default=None),
    supersedes_document_id: uuid.UUID | None = Form(default=None),
) -> DocumentResponse:
    # Read slightly past the limit so oversized uploads are rejected by validation.
    max_bytes = settings.document_max_file_size_bytes
    data = await file.read(max_bytes + 1)
    document = await document_service.create_pending_upload(
        session,
        user,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
        folder_id=folder_id,
        supersedes_document_id=supersedes_document_id,
    )
    # Integration tests use deterministic inline processing; every deployable
    # environment uses the worker-backed path below.
    if settings.app_env == "test":
        document = await document_service.reprocess_document(session, document)
        await document_service._activate_version(session, user, document)  # noqa: SLF001
        await document_service._add_event(  # noqa: SLF001
            session, document=document, actor_user_id=user.id, event_type="version_activated",
            metadata={"background": False, "test_mode": True},
        )
        await session.commit()
        await session.refresh(document)
        return document_service.to_response(document)

    job = await JobService(request.app.state.redis).create_job(
        session,
        owner_user_id=user.id,
        job_type="document.ingestion",
        payload={
            "source": "document_upload",
            "document_id": str(document.id),
            "operation": "ingest",
        },
        idempotency_key=f"document.ingestion:{document.id}",
        max_attempts=3,
    )
    document.background_job_id = job.id
    await session.commit()
    await session.refresh(document)
    return document_service.to_response(document, job)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List the current user's documents",
)
async def list_documents(
    user: CurrentActiveUser,
    session: DbSessionDep,
    document_service: DocumentServiceDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    filename: str | None = Query(default=None, max_length=200),
    folder_id: uuid.UUID | None = Query(default=None),
    archived: bool = Query(default=False),
) -> DocumentListResponse:
    return await document_service.list_documents(
        session,
        user,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        filename=filename,
        folder_id=folder_id,
        archived=archived,
    )


@router.get("/folders", response_model=DocumentFolderListResponse, summary="List document folders")
async def list_document_folders(
    user: CurrentActiveUser, session: DbSessionDep, document_service: DocumentServiceDep
) -> DocumentFolderListResponse:
    return await document_service.list_folders(session, user)


@router.post(
    "/folders", response_model=DocumentFolderResponse, status_code=status.HTTP_201_CREATED,
    summary="Create a document folder",
)
async def create_document_folder(
    payload: DocumentFolderCreate, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentFolderResponse:
    return await document_service.create_folder(session, user, payload)


@router.delete(
    "/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
    summary="Delete a document folder without deleting its documents",
)
async def delete_document_folder(
    folder_id: uuid.UUID, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> Response:
    await document_service.delete_folder(session, user, folder_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{document_id}", response_model=DocumentResponse, summary="Update document metadata")
async def update_document_metadata(
    document_id: uuid.UUID, payload: DocumentMetadataUpdate, user: CurrentActiveUser,
    session: DbSessionDep, document_service: DocumentServiceDep,
) -> DocumentResponse:
    document = await document_service.update_metadata(session, user, document_id, payload)
    return document_service.to_response(document)


@router.post("/{document_id}/archive", response_model=DocumentResponse, summary="Archive a document")
async def archive_document(
    document_id: uuid.UUID, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentResponse:
    document = await document_service.set_archived(session, user, document_id, archived=True)
    return document_service.to_response(document)


@router.post("/{document_id}/restore", response_model=DocumentResponse, summary="Restore an archived document")
async def restore_document(
    document_id: uuid.UUID, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentResponse:
    document = await document_service.set_archived(session, user, document_id, archived=False)
    return document_service.to_response(document)


@router.get(
    "/{document_id}/versions", response_model=DocumentVersionHistoryResponse,
    summary="List immutable versions for a logical knowledge document",
)
async def list_document_versions(
    document_id: uuid.UUID, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentVersionHistoryResponse:
    return await document_service.get_version_history(session, user, document_id)


@router.get(
    "/{document_id}/timeline", response_model=DocumentTimelineResponse,
    summary="List the lifecycle audit timeline for a knowledge document",
)
async def get_document_timeline(
    document_id: uuid.UUID, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentTimelineResponse:
    return await document_service.get_timeline(session, user, document_id)


@router.get(
    "/{document_id}/compare/{other_document_id}", response_model=DocumentVersionCompareResponse,
    summary="Compare metadata and indexing statistics for two versions",
)
async def compare_document_versions(
    document_id: uuid.UUID, other_document_id: uuid.UUID, user: CurrentActiveUser,
    session: DbSessionDep, document_service: DocumentServiceDep,
) -> DocumentVersionCompareResponse:
    return await document_service.compare_versions(session, user, document_id, other_document_id)


@router.post(
    "/{document_id}/reindex", response_model=DocumentResponse,
    summary="Rebuild chunks and embeddings for a document version",
)
async def reindex_document_version(
    document_id: uuid.UUID, request: Request, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentResponse:
    document = await document_service.get_document(session, user, document_id)
    version_token = document.processed_at.isoformat() if document.processed_at else document.updated_at.isoformat()
    job = await JobService(request.app.state.redis).create_job(
        session,
        owner_user_id=user.id,
        job_type="document.reindex",
        payload={
            "source": "document_reindex",
            "document_id": str(document.id),
            "operation": "reindex",
        },
        idempotency_key=f"document.reindex:{document.id}:{version_token}",
        max_attempts=3,
    )
    document.background_job_id = job.id
    await document_service._add_event(  # noqa: SLF001
        session, document=document, actor_user_id=user.id, event_type="reindex_queued",
        metadata={"job_id": str(job.id)},
    )
    await session.commit()
    await session.refresh(document)
    return document_service.to_response(document, job)


@router.post(
    "/{document_id}/activate", response_model=DocumentResponse,
    summary="Activate a ready historical version for RAG",
)
async def activate_document_version(
    document_id: uuid.UUID, user: CurrentActiveUser, session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentResponse:
    document = await document_service.activate_version(session, user, document_id)
    return document_service.to_response(document)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get a document owned by the current user",
)
async def get_document(
    document_id: uuid.UUID,
    user: CurrentActiveUser,
    session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> DocumentResponse:
    document = await document_service.get_document(session, user, document_id)
    job = await document_service.get_background_job(session, document)
    return document_service.to_response(document, job)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a document owned by the current user",
)
async def delete_document(
    document_id: uuid.UUID,
    user: CurrentActiveUser,
    session: DbSessionDep,
    document_service: DocumentServiceDep,
) -> Response:
    await document_service.delete_document(session, user, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
