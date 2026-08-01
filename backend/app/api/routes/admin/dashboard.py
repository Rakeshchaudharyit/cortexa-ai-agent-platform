"""Admin dashboard endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.admin.schemas import AdminDashboardResponse, AdminSystemStatusSummary
from app.api.deps import AdminServiceDep, CurrentAdminUser, DbSessionDep

router = APIRouter()


@router.get("/dashboard", response_model=AdminDashboardResponse, summary="Admin dashboard metrics")
async def admin_dashboard(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    admin: AdminServiceDep,
) -> AdminDashboardResponse:
    health = await admin.get_system_health(session)
    status_map = {c.name: c.status for c in health.components}
    system_status = AdminSystemStatusSummary(
        backend=status_map.get("backend", "unknown"),
        postgres=status_map.get("postgres", "unknown"),
        redis=status_map.get("redis", "unknown"),
        ollama=status_map.get("ollama", "unknown"),
        embedding_model=admin.settings.ollama_embedding_model,
        migrations=status_map.get("migrations", "unknown"),
        storage=status_map.get("storage", "unknown"),
        database_identity=admin.settings.expected_database_identity,
        app_version=admin.settings.app_version,
        environment=admin.settings.app_env,
    )
    return await admin.get_dashboard(session, system_status=system_status)
