"""Admin document endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.admin.schemas import AdminDocumentDetail, AdminDocumentListResponse
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep
from app.core.logging import request_id_ctx
from app.models.enums import DocumentStatus

router = APIRouter()


@router.get("/documents", response_model=AdminDocumentListResponse)
async def list_documents(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    owner_id: uuid.UUID | None = None,
    status: DocumentStatus | None = None,
    media_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminDocumentListResponse:
    return await admin.list_documents(
        session,
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        status=status,
        media_type=media_type,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/documents/{document_id}", response_model=AdminDocumentDetail)
async def get_document(
    document_id: uuid.UUID,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
    include_excerpts: bool = False,
) -> AdminDocumentDetail:
    return await admin.get_document(session, document_id, include_excerpts=include_excerpts)


@router.post("/documents/{document_id}/reprocess", response_model=AdminDocumentDetail)
async def reprocess_document(
    document_id: uuid.UUID,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminDocumentDetail:
    return await admin.reprocess_document(
        session,
        actor=admin_user,
        document_id=document_id,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.delete("/documents/{document_id}", status_code=204, response_class=Response)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    admin_user: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> Response:
    await admin.delete_document(
        session,
        actor=admin_user,
        document_id=document_id,
        request_id=request_id_ctx.get(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)
