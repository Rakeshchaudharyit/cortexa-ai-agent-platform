"""Admin API route package."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.admin import dashboard


def build_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(dashboard.router)
    return router
