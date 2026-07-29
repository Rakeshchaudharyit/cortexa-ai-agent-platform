"""Embedding provider status API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import get_embedding_service
from app.documents.schemas import EmbeddingStatusResponse
from app.services.embeddings import EmbeddingService

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.get(
    "/status",
    response_model=EmbeddingStatusResponse,
    summary="Embedding provider and model availability status",
)
async def embedding_status(request: Request) -> EmbeddingStatusResponse:
    """Report configured embedding provider/model reachability.

    Public by design — does not require authentication (same as LLM status).
    """
    service: EmbeddingService = get_embedding_service(request)
    return await service.status()
