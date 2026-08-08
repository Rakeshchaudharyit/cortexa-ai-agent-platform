"""Administrative background-job monitor APIs."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentAdminUser, DbSessionDep
from app.jobs.schemas import (
    JobBulkActionRequest,
    JobBulkActionResponse,
    JobCreateRequest,
    JobListResponse,
    JobQueueMetrics,
    JobResponse,
)
from app.jobs.service import JobService, serialize_job

router = APIRouter(prefix="/jobs")


def _service(request: Request) -> JobService:
    return JobService(request.app.state.redis)


@router.get("", response_model=JobListResponse)
async def list_admin_jobs(
    request: Request,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=250),
) -> JobListResponse:
    service = _service(request)
    jobs, total = await service.list_jobs(session, status=status, job_type=job_type, limit=limit)
    healthy, seen = await service.worker_health()
    metrics = await service.queue_metrics(session)
    return JobListResponse(
        items=[JobResponse.model_validate(serialize_job(job)) for job in jobs],
        total=total,
        worker_healthy=healthy,
        worker_last_seen_at=seen,
        queue_metrics=JobQueueMetrics(**metrics),
    )


@router.post("/demo", response_model=JobResponse, status_code=201)
async def create_demo_job(
    body: JobCreateRequest,
    request: Request,
    admin: CurrentAdminUser,
    session: DbSessionDep,
) -> JobResponse:
    job = await _service(request).create_job(
        session,
        owner_user_id=admin.id,
        job_type="demo.validation",
        payload=body.payload,
        idempotency_key=body.idempotency_key,
        max_attempts=body.max_attempts,
    )
    return JobResponse.model_validate(serialize_job(job))


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_admin_job(
    job_id: UUID,
    request: Request,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
) -> JobResponse:
    job = await _service(request).cancel_job(session, job_id)
    return JobResponse.model_validate(serialize_job(job))


@router.post("/{job_id}/requeue", response_model=JobResponse)
async def requeue_admin_job(
    job_id: UUID,
    request: Request,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
) -> JobResponse:
    job = await _service(request).requeue_job(session, job_id)
    return JobResponse.model_validate(serialize_job(job))


@router.post("/bulk", response_model=JobBulkActionResponse)
async def bulk_admin_jobs(
    body: JobBulkActionRequest,
    request: Request,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
) -> JobBulkActionResponse:
    changed, skipped = await _service(request).bulk_action(
        session, job_ids=body.job_ids, action=body.action
    )
    return JobBulkActionResponse(
        action=body.action, requested=len(body.job_ids), changed=changed, skipped=skipped
    )
