"""Admin API route package."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.admin import (
    conversations,
    dashboard,
    documents,
    memories,
    users,
)


def build_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(dashboard.router)
    router.include_router(users.router)
    router.include_router(documents.router)
    router.include_router(conversations.router)
    router.include_router(memories.router)
    return router
