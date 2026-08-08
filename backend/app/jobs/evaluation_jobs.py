"""Queue handlers for RAG evaluation execution and CSV exports."""
from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from sqlalchemy import select

from app.db.session import get_session_factory
from app.evaluations.service import RagEvaluationService
from app.models.evaluation import RagEvaluationResult, RagEvaluationRun
from app.models.user import User
from app.services.rag import RagService

Progress = Callable[[int, str], Awaitable[bool]]


async def run_evaluation_job(
    *, rag_service: RagService, run_id: uuid.UUID, progress: Progress
) -> dict[str, object] | None:
    factory = get_session_factory()
    async with factory() as session:
        run = await session.get(RagEvaluationRun, run_id)
        if run is None:
            raise RuntimeError("evaluation_run_not_found")
        actor = await session.get(User, run.created_by_user_id) if run.created_by_user_id else None
        if actor is None:
            raise RuntimeError("evaluation_actor_not_found")
        service = RagEvaluationService(rag_service=rag_service)
        completed = await service.run(session, actor=actor, run=run, progress=progress)
        if completed.status == "cancelled":
            return None
        return {
            "run_id": str(completed.id),
            "total_cases": completed.total_cases,
            "passed_cases": completed.passed_cases,
            "failed_cases": completed.failed_cases,
            "average_score": completed.average_score,
        }


async def export_evaluation_csv_job(
    *, run_id: uuid.UUID, job_id: uuid.UUID, storage_root: str, progress: Progress
) -> dict[str, object] | None:
    if not await progress(10, "Loading evaluation results"):
        return None
    factory = get_session_factory()
    async with factory() as session:
        run = await session.get(RagEvaluationRun, run_id)
        if run is None:
            raise RuntimeError("evaluation_run_not_found")
        results = list(
            (
                await session.scalars(
                    select(RagEvaluationResult)
                    .where(RagEvaluationResult.run_id == run_id)
                    .order_by(RagEvaluationResult.created_at.asc())
                )
            ).all()
        )
    if not await progress(55, "Building CSV export"):
        return None
    export_dir = Path(storage_root) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"rag-evaluation-{run_id}-{job_id}.csv"
    path = export_dir / filename
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "case_name", "status", "passed", "score", "groundedness", "keyword_recall",
            "citation_match", "answerability", "retrieval_count", "citation_count",
            "latency_ms", "provider", "model", "error_code",
        ])
        for item in results:
            writer.writerow([
                item.case_name, item.status, item.passed, item.score, item.groundedness_score,
                item.keyword_recall_score, item.citation_match_score, item.answerability_score,
                item.retrieval_count, item.citation_count, item.latency_ms or "", item.provider or "",
                item.model or "", item.error_code or "",
            ])
    if not await progress(90, "Finalizing export"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return {
        "run_id": str(run_id),
        "filename": filename,
        "row_count": len(results),
        "download_ready": True,
    }
