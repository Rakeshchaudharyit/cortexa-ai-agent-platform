"""Top-level API router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, documents, embeddings, health, llm, rag, system
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    """Compose versioned API routes under the configured prefix."""
    api = APIRouter(prefix=settings.api_prefix)
    api.include_router(system.router)
    api.include_router(auth.router)
    api.include_router(llm.router)
    api.include_router(documents.router)
    api.include_router(rag.router)
    api.include_router(embeddings.router)
    return api


def build_root_router() -> APIRouter:
    """Compose root-level health/readiness routes."""
    root = APIRouter()
    root.include_router(health.router)
    return root
