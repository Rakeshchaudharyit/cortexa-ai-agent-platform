"""Authenticated user background-job APIs."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from app.api.deps import CurrentActiveUser, DbSessionDep
from app.core.exceptions import AppError
from app.jobs.schemas import JobCreateRequest, JobListResponse, JobResponse
from app.jobs.service import JobService, serialize_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _service(request: Request) -> JobService:
    return JobService(request.app.state.redis)


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreateRequest,
    request: Request,
    user: CurrentActiveUser,
    session: DbSessionDep,
) -> JobResponse:
    if body.job_type != "demo.validation":
        raise AppError(
            code="job_submission_not_allowed",
            message="This job type must be created through its owning feature API",
            status_code=403,
        )
    job = await _service(request).create_job(
        session,
        owner_user_id=user.id,
        job_type=body.job_type,
        payload=body.payload,
        idempotency_key=body.idempotency_key,
        max_attempts=body.max_attempts,
    )
    return JobResponse.model_validate(serialize_job(job))


@router.get("", response_model=JobListResponse)
async def list_jobs(request: Request, user: CurrentActiveUser, session: DbSessionDep) -> JobListResponse:
    service = _service(request)
    jobs, total = await service.list_jobs(session, owner_user_id=user.id)
    healthy, seen = await service.worker_health()
    return JobListResponse(
        items=[JobResponse.model_validate(serialize_job(job)) for job in jobs],
        total=total,
        worker_healthy=healthy,
        worker_last_seen_at=seen,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, request: Request, user: CurrentActiveUser, session: DbSessionDep) -> JobResponse:
    job = await _service(request).get_job(session, job_id, owner_user_id=user.id)
    return JobResponse.model_validate(serialize_job(job))


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: UUID, request: Request, user: CurrentActiveUser, session: DbSessionDep) -> JobResponse:
    job = await _service(request).cancel_job(session, job_id, owner_user_id=user.id)
    return JobResponse.model_validate(serialize_job(job))
