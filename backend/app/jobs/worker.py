"""Standalone Redis-backed background worker."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.documents.chunking import ChunkingConfig, ChunkingService
from app.documents.extraction import ExtractionService
from app.embeddings.factory import create_embedding_provider
from app.llm.factory import create_llm_provider
from app.jobs.evaluation_jobs import export_evaluation_csv_job, run_evaluation_job
from app.jobs.document_ingestion import (
    DocumentFinalizationError,
    mark_document_job_terminal,
    process_document_job,
)
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.jobs.service import DELAYED_KEY, QUEUE_KEY, WORKER_HEARTBEAT_KEY
from app.models.enums import JobStatus
from app.models.evaluation import RagEvaluationRun
from app.models.job import BackgroundJob
from app.providers.http import close_http_client, init_http_client
from app.providers.redis import close_redis, init_redis
from app.services.documents import DocumentService
from app.services.llm import LLMService
from app.services.rag import RagService
from app.services.retrieval import RetrievalService
from app.storage.local import LocalFilesystemStorage

logger = logging.getLogger("cortexa.jobs.worker")


def _safe_exception_fields(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, DocumentFinalizationError):
        return exc.code[:64], f"Document finalization failed during {exc.stage}"[:512]
    if isinstance(exc, DBAPIError):
        original = getattr(exc, "orig", None)
        detail = str(original or exc).replace("\n", " ").strip()
        return "database_error", (detail[:512] or "Database operation failed")
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    return (str(code or type(exc).__name__).lower()[:64], str(message or exc or "Background job failed")[:512])


async def _set_progress(job_id: uuid.UUID, percent: int, message: str) -> bool:
    factory = get_session_factory()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            return False
        if job.cancellation_requested:
            job.status = JobStatus.cancelled.value
            job.status_message = "Cancelled"
            job.finished_at = datetime.now(UTC)
            await session.commit()
            return False
        job.progress_percent = percent
        job.status_message = message
        job.heartbeat_at = datetime.now(UTC)
        await session.commit()
        return True


async def _job_heartbeat(job_id: uuid.UUID) -> None:
    factory = get_session_factory()
    while True:
        await asyncio.sleep(10)
        async with factory() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is None or job.status != JobStatus.running.value:
                return
            job.heartbeat_at = datetime.now(UTC)
            await session.commit()


async def _run_demo(job_id: uuid.UUID) -> dict[str, object] | None:
    steps = [
        (10, "Validation started"),
        (35, "Checking queue transport"),
        (65, "Checking durable progress"),
        (90, "Finalizing validation"),
    ]
    for percent, message in steps:
        if not await _set_progress(job_id, percent, message):
            return None
        await asyncio.sleep(2)
    return {"validated": True, "checks": len(steps)}


async def _mark_evaluation_terminal(job_id: uuid.UUID, *, failed: bool = False, cancelled: bool = False, message: str | None = None) -> None:
    factory = get_session_factory()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None or not job.job_type.startswith("evaluation."):
            return
        raw = job.payload_json.get("run_id")
        if not raw:
            return
        try:
            run_id = uuid.UUID(str(raw))
        except ValueError:
            return
        run = await session.get(RagEvaluationRun, run_id)
        if run is None:
            return
        if cancelled:
            run.status = "cancelled"
            run.error_summary = "Evaluation cancelled"
        elif failed:
            run.status = "failed"
            run.error_summary = (message or "Background evaluation failed")[:500]
        await session.commit()


async def _execute(
    job_id: uuid.UUID, worker_id: str, redis: Redis[Any], document_service: DocumentService, rag_service: RagService, storage_root: str
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        job = await session.scalar(
            select(BackgroundJob)
            .where(
                BackgroundJob.id == job_id,
                BackgroundJob.status.in_([JobStatus.queued.value, JobStatus.retrying.value]),
            )
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return
        if job.cancellation_requested:
            job.status = JobStatus.cancelled.value
            job.finished_at = datetime.now(UTC)
            await session.commit()
            return
        job.status = JobStatus.running.value
        job.attempt_count += 1
        job.locked_by = worker_id
        job.started_at = job.started_at or datetime.now(UTC)
        job.heartbeat_at = datetime.now(UTC)
        job.status_message = "Worker accepted job"
        await session.commit()
        job_type = job.job_type
        attempt = job.attempt_count
        max_attempts = job.max_attempts

    job_heartbeat_task = asyncio.create_task(_job_heartbeat(job_id))
    try:
        if job_type == "demo.validation":
            result = await _run_demo(job_id)
        elif job_type in {"document.ingestion", "document.reindex"}:
            async with factory() as session:
                current = await session.get(BackgroundJob, job_id)
                if current is None:
                    return
                document_id = uuid.UUID(str(current.payload_json.get("document_id")))
                operation = str(current.payload_json.get("operation") or "ingest")
            result = await process_document_job(
                document_service=document_service,
                document_id=document_id,
                operation=operation,
                progress=lambda percent, message: _set_progress(job_id, percent, message),
            )
            if result is None:
                await mark_document_job_terminal(
                    document_id=document_id, operation=operation,
                    error_code="cancelled", cancelled=True,
                )
                return
        elif job_type == "evaluation.run":
            async with factory() as session:
                current = await session.get(BackgroundJob, job_id)
                if current is None:
                    return
                run_id = uuid.UUID(str(current.payload_json.get("run_id")))
            result = await run_evaluation_job(
                rag_service=rag_service, run_id=run_id,
                progress=lambda percent, message: _set_progress(job_id, percent, message),
            )
            if result is None:
                await _mark_evaluation_terminal(job_id, cancelled=True)
                return
        elif job_type == "evaluation.export":
            async with factory() as session:
                current = await session.get(BackgroundJob, job_id)
                if current is None:
                    return
                run_id = uuid.UUID(str(current.payload_json.get("run_id")))
            result = await export_evaluation_csv_job(
                run_id=run_id, job_id=job_id, storage_root=storage_root,
                progress=lambda percent, message: _set_progress(job_id, percent, message),
            )
            if result is None:
                return
        else:
            raise RuntimeError("unsupported_job_type")
        async with factory() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is None or job.status == JobStatus.cancelled.value:
                return
            job.status = JobStatus.succeeded.value
            job.progress_percent = 100
            job.status_message = "Completed successfully"
            job.result_json = result or {}
            job.finished_at = datetime.now(UTC)
            job.heartbeat_at = datetime.now(UTC)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        error_code, error_message = _safe_exception_fields(exc)
        logger.exception(
            "job_execution_failed job_id=%s job_type=%s error_code=%s error_message=%s",
            job_id,
            job_type,
            error_code,
            error_message,
        )
        async with factory() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                return
            if job_type in {"document.ingestion", "document.reindex"} and attempt >= max_attempts:
                try:
                    document_id = uuid.UUID(str(job.payload_json.get("document_id")))
                    operation = str(job.payload_json.get("operation") or "ingest")
                    await mark_document_job_terminal(
                        document_id=document_id, operation=operation,
                        error_code=error_code,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("document_job_terminal_update_failed job_id=%s", job_id)
            if job_type == "evaluation.run" and attempt >= max_attempts:
                await _mark_evaluation_terminal(job_id, failed=True, message=error_message)
            if attempt < max_attempts:
                delay = min(60, 2 ** max(1, attempt))
                job.status = JobStatus.retrying.value
                job.status_message = f"Retry scheduled in {delay}s"
                job.error_code = error_code
                job.error_message = error_message
                job.available_at = datetime.now(UTC) + timedelta(seconds=delay)
                await session.commit()
                await redis.zadd(DELAYED_KEY, {str(job_id): job.available_at.timestamp()})
            else:
                job.status = JobStatus.dead_lettered.value
                job.status_message = "Moved to dead letter after maximum attempts"
                job.error_code = error_code
                job.error_message = error_message
                job.finished_at = datetime.now(UTC)
                await session.commit()
    finally:
        job_heartbeat_task.cancel()
        await asyncio.gather(job_heartbeat_task, return_exceptions=True)


async def _recover_durable_jobs(redis: Redis[Any]) -> int:
    """Recover interrupted work and restore Redis delivery from PostgreSQL."""
    factory = get_session_factory()
    recovered = 0
    async with factory() as session:
        jobs = list(
            (
                await session.scalars(
                    select(BackgroundJob).where(
                        or_(
                            BackgroundJob.status.in_(
                                [JobStatus.queued.value, JobStatus.retrying.value]
                            ),
                            (
                                (BackgroundJob.status == JobStatus.running.value)
                                & (
                                    (BackgroundJob.heartbeat_at.is_(None))
                                    | (
                                        BackgroundJob.heartbeat_at
                                        < datetime.now(UTC) - timedelta(seconds=45)
                                    )
                                )
                            ),
                        )
                    )
                )
            ).all()
        )
        now = datetime.now(UTC)
        for job in jobs:
            if job.cancellation_requested:
                job.status = JobStatus.cancelled.value
                job.status_message = "Cancelled during recovery"
                job.finished_at = now
                continue
            if job.status == JobStatus.running.value:
                job.status = JobStatus.queued.value
                job.status_message = "Recovered after worker restart"
                job.available_at = now
            job.locked_by = None
            if job.status == JobStatus.retrying.value and job.available_at > now:
                await redis.zadd(DELAYED_KEY, {str(job.id): job.available_at.timestamp()})
            else:
                job.status = JobStatus.queued.value
                await redis.rpush(QUEUE_KEY, str(job.id))
            recovered += 1
        await session.commit()
    return recovered


async def _promote_delayed(redis: Redis[Any]) -> None:
    now = datetime.now(UTC).timestamp()
    ids = await redis.zrangebyscore(DELAYED_KEY, 0, now, start=0, num=100)
    if ids:
        pipe = redis.pipeline()
        for value in ids:
            pipe.rpush(QUEUE_KEY, value)
            pipe.zrem(DELAYED_KEY, value)
        await pipe.execute()


async def _heartbeat(redis: Redis[Any]) -> None:
    while True:
        await redis.set(WORKER_HEARTBEAT_KEY, datetime.now(UTC).isoformat(), ex=45)
        await asyncio.sleep(10)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_engine(settings)
    redis = await init_redis(settings)
    http_client = await init_http_client(settings)
    embedding_provider = create_embedding_provider(settings, http_client)
    document_service = DocumentService(
        settings=settings,
        storage=LocalFilesystemStorage(root_path=settings.document_storage_path),
        extraction_service=ExtractionService(settings),
        chunking_service=ChunkingService(
            ChunkingConfig(
                chunk_size=settings.chunk_size_characters,
                overlap=settings.chunk_overlap_characters,
                min_characters=settings.chunk_min_characters,
                max_chunks=settings.document_max_chunks,
            )
        ),
        embedding_provider=embedding_provider,
    )
    llm_provider = create_llm_provider(settings, http_client)
    llm_service = LLMService(settings=settings, provider=llm_provider)
    retrieval_service = RetrievalService(settings=settings, embedding_provider=embedding_provider)
    rag_service = RagService(settings=settings, retrieval_service=retrieval_service, llm_service=llm_service)
    worker_id = os.getenv("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    logger.info("worker_started worker_id=%s", worker_id)
    recovered = await _recover_durable_jobs(redis)
    if recovered:
        logger.warning("worker_jobs_recovered count=%s", recovered)
    heartbeat_task = asyncio.create_task(_heartbeat(redis))
    last_recovery = asyncio.get_running_loop().time()
    try:
        while True:
            now_monotonic = asyncio.get_running_loop().time()
            if now_monotonic - last_recovery >= 30:
                await _recover_durable_jobs(redis)
                last_recovery = now_monotonic
            await _promote_delayed(redis)
            item = await redis.blpop(QUEUE_KEY, timeout=5)
            if item:
                _, raw_id = item
                try:
                    await _execute(uuid.UUID(str(raw_id)), worker_id, redis, document_service, rag_service, settings.document_storage_path)
                except ValueError:
                    logger.error("invalid_job_id payload=%s", raw_id)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        await close_http_client()
        await close_redis()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
