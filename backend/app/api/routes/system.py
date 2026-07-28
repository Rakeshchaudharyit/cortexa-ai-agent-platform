"""System information routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.common import SystemInfoResponse
from app.services.health import HealthService

router = APIRouter(prefix="/system", tags=["system"])


def _health_service(request: Request) -> HealthService:
    service = request.app.state.health_service
    if not isinstance(service, HealthService):
        raise RuntimeError("Health service is not configured")
    return service


@router.get(
    "/info",
    response_model=SystemInfoResponse,
    summary="Non-sensitive application information",
)
async def system_info(request: Request) -> SystemInfoResponse:
    return _health_service(request).system_info()
