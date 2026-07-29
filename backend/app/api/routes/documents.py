"""Document upload, list, detail, and delete API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.deps import CurrentActiveUser, DbSessionDep, DocumentServiceDep, SettingsDep
from app.documents.schemas import DocumentListResponse, DocumentResponse
from app.models.enums import DocumentStatus

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and synchronously ingest a document",
)
async def upload_document(
    user: CurrentActiveUser,
    session: DbSessionDep,
    settings: SettingsDep,
    document_service: DocumentServiceDep,
    file: UploadFile = File(...),
) -> DocumentResponse:
    # Read slightly past the limit so oversized uploads are rejected by validation.
    max_bytes = settings.document_max_file_size_bytes
    data = await file.read(max_bytes + 1)
    document = await document_service.ingest(
        session,
        user,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    )
    return document_service.to_response(document)


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
) -> DocumentListResponse:
    return await document_service.list_documents(
        session,
        user,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        filename=filename,
    )


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
    return document_service.to_response(document)


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
