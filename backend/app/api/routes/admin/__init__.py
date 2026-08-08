"""Admin API route package."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.admin import (
    agents,
    analytics,
    audit,
    conversations,
    dashboard,
    documents,
    evaluations,
    feedback,
    jobs,
    memories,
    settings,
    system,
    tools,
    users,
)


def build_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(dashboard.router)
    router.include_router(agents.router)
    router.include_router(users.router)
    router.include_router(documents.router)
    router.include_router(evaluations.router)
    router.include_router(feedback.router)
    router.include_router(jobs.router)
    router.include_router(conversations.router)
    router.include_router(memories.router)
    router.include_router(tools.router)
    router.include_router(analytics.router)
    router.include_router(audit.router)
    router.include_router(system.router)
    router.include_router(settings.router)
    return router
