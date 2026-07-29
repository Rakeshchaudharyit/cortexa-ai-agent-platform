"""Grounded RAG query API routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentActiveUser, DbSessionDep, RagServiceDep
from app.documents.schemas import RagQueryRequest, RagQueryResponse

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post(
    "/query",
    response_model=RagQueryResponse,
    summary="Ask a grounded question over the current user's documents",
)
async def rag_query(
    body: RagQueryRequest,
    user: CurrentActiveUser,
    session: DbSessionDep,
    rag_service: RagServiceDep,
) -> RagQueryResponse:
    return await rag_service.query(session, user, body)
