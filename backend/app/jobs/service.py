"""Durable PostgreSQL job ledger with Redis delivery."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import JobStatus
from app.models.job import BackgroundJob

logger = logging.getLogger("cortexa.jobs")
QUEUE_KEY = "cortexa:jobs:ready"
DELAYED_KEY = "cortexa:jobs:delayed"
WORKER_HEARTBEAT_KEY = "cortexa:jobs:worker:heartbeat"
ALLOWED_JOB_TYPES = frozenset({"demo.validation", "document.ingestion", "document.reindex", "evaluation.run", "evaluation.export"})
TERMINAL_STATUSES = frozenset({JobStatus.succeeded.value, JobStatus.failed.value, JobStatus.dead_lettered.value, JobStatus.cancelled.value})


class JobService:
    def __init__(self, redis: Redis[Any]) -> None:
        self.redis = redis

    async def create_job(
        self,
        session: AsyncSession,
        *,
        owner_user_id: uuid.UUID | None,
        job_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
        max_attempts: int,
    ) -> BackgroundJob:
        if job_type not in ALLOWED_JOB_TYPES:
            raise AppError(code="unsupported_job_type", message="Unsupported job type", status_code=422)
        if idempotency_key:
            existing = await session.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.owner_user_id == owner_user_id,
                    BackgroundJob.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.status in {JobStatus.queued.value, JobStatus.retrying.value}:
                    await self.enqueue(existing.id)
                return existing
        safe_payload: dict[str, Any] = {"source": str(payload.get("source", "api"))[:80]}
        if job_type in {"document.ingestion", "document.reindex"}:
            document_id = payload.get("document_id")
            operation = payload.get("operation")
            try:
                safe_payload["document_id"] = str(uuid.UUID(str(document_id)))
            except (TypeError, ValueError, AttributeError) as exc:
                raise AppError(
                    code="invalid_document_job_payload",
                    message="Document job requires a valid document ID",
                    status_code=422,
                ) from exc
            safe_payload["operation"] = str(operation or "ingest")[:32]
        elif job_type in {"evaluation.run", "evaluation.export"}:
            key = "run_id"
            try:
                safe_payload[key] = str(uuid.UUID(str(payload.get(key))))
            except (TypeError, ValueError, AttributeError) as exc:
                raise AppError(
                    code="invalid_evaluation_job_payload",
                    message="Evaluation job requires a valid run ID",
                    status_code=422,
                ) from exc
        job = BackgroundJob(
            owner_user_id=owner_user_id,
            job_type=job_type,
            payload_json=safe_payload,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            status=JobStatus.queued.value,
            status_message="Waiting for a worker",
        )
        session.add(job)
        try:
            await session.flush()
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if not idempotency_key:
                raise
            existing = await session.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.owner_user_id == owner_user_id,
                    BackgroundJob.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            if existing.status in {JobStatus.queued.value, JobStatus.retrying.value}:
                await self.enqueue(existing.id)
            return existing
        try:
            await self.enqueue(job.id)
        except Exception:  # noqa: BLE001
            logger.exception("job_enqueue_failed job_id=%s", job.id)
        logger.info("job_created job_id=%s job_type=%s", job.id, job.job_type)
        return job

    async def enqueue(self, job_id: uuid.UUID) -> None:
        await self.redis.rpush(QUEUE_KEY, str(job_id))

    async def list_jobs(
        self,
        session: AsyncSession,
        *,
        owner_user_id: uuid.UUID | None = None,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
    ) -> tuple[list[BackgroundJob], int]:
        filters: list[Any] = []
        if owner_user_id is not None:
            filters.append(BackgroundJob.owner_user_id == owner_user_id)
        if status:
            filters.append(BackgroundJob.status == status)
        if job_type:
            filters.append(BackgroundJob.job_type == job_type)
        stmt = (
            select(BackgroundJob)
            .where(*filters)
            .order_by(BackgroundJob.created_at.desc())
            .limit(limit)
        )
        rows = list((await session.scalars(stmt)).all())
        total_query = select(func.count()).select_from(BackgroundJob).where(*filters)
        total = int(await session.scalar(total_query) or 0)
        return rows, total

    async def get_job(
        self, session: AsyncSession, job_id: uuid.UUID, *, owner_user_id: uuid.UUID | None = None
    ) -> BackgroundJob:
        stmt = select(BackgroundJob).where(BackgroundJob.id == job_id)
        if owner_user_id is not None:
            stmt = stmt.where(BackgroundJob.owner_user_id == owner_user_id)
        job = await session.scalar(stmt)
        if job is None:
            raise AppError(code="job_not_found", message="Job not found", status_code=404)
        return job

    async def cancel_job(
        self, session: AsyncSession, job_id: uuid.UUID, *, owner_user_id: uuid.UUID | None = None
    ) -> BackgroundJob:
        job = await self.get_job(session, job_id, owner_user_id=owner_user_id)
        if job.status in TERMINAL_STATUSES:
            return job
        job.cancellation_requested = True
        if job.status in {JobStatus.queued.value, JobStatus.retrying.value}:
            job.status = JobStatus.cancelled.value
            job.progress_percent = min(job.progress_percent, 99)
            job.status_message = "Cancelled before execution"
            job.finished_at = datetime.now(UTC)
        await session.commit()
        if job.status == JobStatus.cancelled.value and job.job_type in {"document.ingestion", "document.reindex"}:
            try:
                from app.jobs.document_ingestion import mark_document_job_terminal

                await mark_document_job_terminal(
                    document_id=uuid.UUID(str(job.payload_json.get("document_id"))),
                    operation=str(job.payload_json.get("operation") or "ingest"),
                    error_code="cancelled",
                    cancelled=True,
                )
            except Exception:  # noqa: BLE001
                logger.exception("document_job_cancel_update_failed job_id=%s", job.id)
        elif job.status == JobStatus.cancelled.value and job.job_type == "evaluation.run":
            try:
                from app.models.evaluation import RagEvaluationRun

                run = await session.get(RagEvaluationRun, uuid.UUID(str(job.payload_json.get("run_id"))))
                if run is not None:
                    run.status = "cancelled"
                    run.error_summary = "Evaluation cancelled"
                    await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("evaluation_job_cancel_update_failed job_id=%s", job.id)
        return job


    async def queue_metrics(self, session: AsyncSession) -> dict[str, int | None]:
        now = datetime.now(UTC)
        stale_cutoff = now - timedelta(seconds=45)
        ready_depth = int(await self.redis.llen(QUEUE_KEY) or 0)
        delayed_depth = int(await self.redis.zcard(DELAYED_KEY) or 0)
        dead_letter_count = int(
            await session.scalar(
                select(func.count()).select_from(BackgroundJob).where(
                    BackgroundJob.status.in_([JobStatus.dead_lettered.value, JobStatus.failed.value])
                )
            ) or 0
        )
        stale_running_count = int(
            await session.scalar(
                select(func.count()).select_from(BackgroundJob).where(
                    BackgroundJob.status == JobStatus.running.value,
                    (BackgroundJob.heartbeat_at.is_(None)) | (BackgroundJob.heartbeat_at < stale_cutoff),
                )
            ) or 0
        )
        oldest = await session.scalar(
            select(func.min(BackgroundJob.created_at)).where(
                BackgroundJob.status.in_([JobStatus.queued.value, JobStatus.retrying.value])
            )
        )
        oldest_age = max(0, int((now - oldest).total_seconds())) if oldest is not None else None
        return {
            "ready_depth": ready_depth,
            "delayed_depth": delayed_depth,
            "dead_letter_count": dead_letter_count,
            "stale_running_count": stale_running_count,
            "oldest_queued_age_seconds": oldest_age,
        }

    async def requeue_job(
        self, session: AsyncSession, job_id: uuid.UUID, *, owner_user_id: uuid.UUID | None = None
    ) -> BackgroundJob:
        job = await self.get_job(session, job_id, owner_user_id=owner_user_id)
        if job.status not in {JobStatus.failed.value, JobStatus.dead_lettered.value}:
            raise AppError(
                code="job_not_requeueable",
                message="Only failed or dead-lettered jobs can be requeued",
                status_code=409,
            )
        await self._prepare_resource_for_requeue(session, job)
        job.status = JobStatus.queued.value
        job.progress_percent = 0
        job.status_message = "Requeued by administrator"
        job.error_code = None
        job.error_message = None
        job.attempt_count = 0
        job.cancellation_requested = False
        job.locked_by = None
        job.available_at = datetime.now(UTC)
        job.started_at = None
        job.heartbeat_at = None
        job.finished_at = None
        await session.commit()
        await self.enqueue(job.id)
        logger.info("job_requeued job_id=%s job_type=%s", job.id, job.job_type)
        return job

    async def bulk_action(
        self, session: AsyncSession, *, job_ids: list[uuid.UUID], action: str
    ) -> tuple[int, int]:
        changed = 0
        skipped = 0
        for job_id in dict.fromkeys(job_ids):
            try:
                if action == "cancel":
                    job = await self.get_job(session, job_id)
                    if job.status in TERMINAL_STATUSES:
                        skipped += 1
                        continue
                    await self.cancel_job(session, job_id)
                elif action == "requeue":
                    job = await self.get_job(session, job_id)
                    if job.status not in {JobStatus.failed.value, JobStatus.dead_lettered.value}:
                        skipped += 1
                        continue
                    await self.requeue_job(session, job_id)
                else:
                    raise AppError(code="invalid_bulk_action", message="Unsupported bulk action", status_code=422)
                changed += 1
            except AppError as exc:
                if exc.status_code in {404, 409}:
                    skipped += 1
                    continue
                raise
        return changed, skipped

    async def _prepare_resource_for_requeue(self, session: AsyncSession, job: BackgroundJob) -> None:
        if job.job_type in {"document.ingestion", "document.reindex"}:
            from app.models.document import Document
            from app.models.enums import DocumentStatus

            raw = job.payload_json.get("document_id")
            if not raw:
                return
            document = await session.get(Document, uuid.UUID(str(raw)))
            if document is None:
                return
            if job.job_type == "document.ingestion":
                document.status = DocumentStatus.pending
                document.lifecycle_state = "processing"
                document.error_code = None
                document.error_message = None
            else:
                document.error_code = None
                document.error_message = None
        elif job.job_type == "evaluation.run":
            from app.models.evaluation import RagEvaluationRun

            raw = job.payload_json.get("run_id")
            if not raw:
                return
            run = await session.get(RagEvaluationRun, uuid.UUID(str(raw)))
            if run is not None:
                run.status = "queued"
                run.error_summary = None
                run.completed_at = None

    async def worker_health(self) -> tuple[bool, datetime | None]:
        raw = await self.redis.get(WORKER_HEARTBEAT_KEY)
        if not raw:
            return False, None
        try:
            seen = datetime.fromisoformat(str(raw))
        except ValueError:
            return False, None
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        return datetime.now(UTC) - seen <= timedelta(seconds=30), seen


def serialize_job(job: BackgroundJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "owner_user_id": job.owner_user_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress_percent": job.progress_percent,
        "status_message": job.status_message,
        "result": job.result_json,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "cancellation_requested": job.cancellation_requested,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "updated_at": job.updated_at,
        "resource_type": ("document" if job.job_type.startswith("document.") else "evaluation" if job.job_type.startswith("evaluation.") else None),
        "resource_id": (job.payload_json.get("document_id") if job.job_type.startswith("document.") else job.payload_json.get("run_id") if job.job_type.startswith("evaluation.") else None),
    }
