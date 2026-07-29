"""Liveness and readiness routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])


def _health_service(request: Request) -> HealthService:
    service = request.app.state.health_service
    if not isinstance(service, HealthService):
        raise RuntimeError("Health service is not configured")
    return service


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
)
@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Liveness probe (alias)",
    include_in_schema=False,
)
async def health(request: Request) -> HealthResponse:
    """Process liveness — does not depend on PostgreSQL or Redis."""
    return _health_service(request).liveness()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={
        200: {"description": "All required dependencies reachable"},
        503: {"description": "One or more required dependencies unavailable"},
    },
)
@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (alias)",
    include_in_schema=False,
    responses={
        200: {"description": "All required dependencies reachable"},
        503: {"description": "One or more required dependencies unavailable"},
    },
)
async def ready(request: Request) -> Response:
    """Readiness — Postgres (connectivity, migrations, schema) and Redis."""
    body, status_code = await _health_service(request).readiness()
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
    )
