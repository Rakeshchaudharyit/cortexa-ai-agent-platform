"""RAG evaluation runner and deterministic scoring policy."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.schemas import RagQueryRequest
from app.models.evaluation import RagEvaluationCase, RagEvaluationResult, RagEvaluationRun
from app.models.user import User
from app.services.rag import RagService

logger = logging.getLogger("cortexa.rag_evaluation")


@dataclass(frozen=True)
class CaseScores:
    groundedness: float
    keyword_recall: float
    citation_match: float
    answerability: float
    overall: float
    passed: bool


def _bounded_excerpt(value: str, limit: int = 500) -> str:
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def score_case(
    case: RagEvaluationCase,
    *,
    answer: str,
    grounded: bool,
    citation_document_ids: set[str],
    citation_count: int,
) -> CaseScores:
    lowered = answer.casefold()
    keywords = [item.strip().casefold() for item in case.expected_keywords_json if item.strip()]
    if not keywords and case.expected_answer:
        keywords = list(dict.fromkeys(
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9_-]+", case.expected_answer)
            if len(token) >= 4
        ))[:20]
    keyword_recall = (
        sum(1 for item in keywords if item in lowered) / len(keywords) if keywords else 1.0
    )

    expected_docs = set(case.expected_document_ids_json)
    citation_match = (
        len(expected_docs & citation_document_ids) / len(expected_docs) if expected_docs else 1.0
    )

    if case.should_answer:
        answerability = 1.0 if grounded and citation_count > 0 else 0.0
        groundedness = 1.0 if grounded and citation_count > 0 else 0.0
    else:
        no_answer_language = any(
            marker in lowered
            for marker in ("couldn’t find", "could not find", "not available", "insufficient")
        )
        answerability = 1.0 if (not grounded and citation_count == 0 and no_answer_language) else 0.0
        groundedness = 1.0 if not grounded and citation_count == 0 else 0.0

    overall = round(
        (groundedness * 0.35)
        + (keyword_recall * 0.30)
        + (citation_match * 0.20)
        + (answerability * 0.15),
        4,
    )
    return CaseScores(
        groundedness=round(groundedness, 4),
        keyword_recall=round(keyword_recall, 4),
        citation_match=round(citation_match, 4),
        answerability=round(answerability, 4),
        overall=overall,
        passed=overall >= 0.75,
    )


@dataclass
class RagEvaluationService:
    rag_service: RagService

    async def create_run(self, session: AsyncSession, *, actor: User) -> RagEvaluationRun:
        total = int(
            await session.scalar(
                select(func.count()).select_from(RagEvaluationCase).where(RagEvaluationCase.enabled.is_(True))
            ) or 0
        )
        run = RagEvaluationRun(created_by_user_id=actor.id, status="queued", total_cases=total)
        session.add(run)
        await session.flush()
        return run

    async def run(
        self,
        session: AsyncSession,
        *,
        actor: User,
        run: RagEvaluationRun | None = None,
        progress: Callable[[int, str], Awaitable[bool]] | None = None,
    ) -> RagEvaluationRun:
        cases = list(
            (
                await session.scalars(
                    select(RagEvaluationCase)
                    .where(RagEvaluationCase.enabled.is_(True))
                    .order_by(RagEvaluationCase.created_at.asc(), RagEvaluationCase.id.asc())
                )
            ).all()
        )
        if run is None:
            run = RagEvaluationRun(created_by_user_id=actor.id, status="running", total_cases=len(cases))
            session.add(run)
            await session.flush()
        else:
            run.status = "running"
            run.total_cases = len(cases)
            run.passed_cases = 0
            run.failed_cases = 0
            run.average_score = 0.0
            run.completed_at = None
            run.error_summary = None
            await session.execute(delete(RagEvaluationResult).where(RagEvaluationResult.run_id == run.id))
            await session.flush()
        started = time.perf_counter()
        scores: list[float] = []

        if progress and not await progress(5, "Evaluation started"):
            run.status = "cancelled"
            await session.commit()
            return run

        for index, case in enumerate(cases, start=1):
            await self._execute_case(session, run=run, case=case, scores=scores)
            await session.flush()
            if progress:
                percent = 10 + int((index / max(1, len(cases))) * 80)
                if not await progress(percent, f"Evaluated {index}/{len(cases)} cases"):
                    run.status = "cancelled"
                    await session.commit()
                    return run

        run.passed_cases = sum(1 for value in scores if value >= 0.75)
        run.failed_cases = len(scores) - run.passed_cases
        run.average_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        run.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(run)
        logger.info(
            "rag_evaluation_completed run_id=%s total=%s passed=%s score=%s duration_ms=%s",
            run.id, run.total_cases, run.passed_cases, run.average_score, run.duration_ms,
        )
        return run

    async def _execute_case(
        self, session: AsyncSession, *, run: RagEvaluationRun, case: RagEvaluationCase, scores: list[float]
    ) -> None:
        owner = await session.get(User, case.owner_user_id)
        if owner is None:
            self._record_error(session, run, case, "owner_not_found")
            scores.append(0.0)
            return
        try:
            response = await self.rag_service.query(session, owner, RagQueryRequest(question=case.question))
            citation_docs = {str(item.document_id) for item in response.citations}
            scored = score_case(
                case, answer=response.answer, grounded=response.grounded,
                citation_document_ids=citation_docs, citation_count=len(response.citations),
            )
            scores.append(scored.overall)
            session.add(RagEvaluationResult(
                run_id=run.id, case_id=case.id, case_name=case.name, status="completed",
                score=scored.overall, passed=scored.passed, groundedness_score=scored.groundedness,
                keyword_recall_score=scored.keyword_recall, citation_match_score=scored.citation_match,
                answerability_score=scored.answerability, retrieval_count=response.retrieval_count,
                citation_count=len(response.citations), latency_ms=response.latency_ms, provider=response.provider,
                model=response.model, answer_excerpt=_bounded_excerpt(response.answer),
                metrics_json={"expected_keyword_count": len(case.expected_keywords_json)},
            ))
            run.provider = run.provider or response.provider
            run.model = run.model or response.model
        except Exception as exc:  # noqa: BLE001
            logger.exception("rag_evaluation_case_failed run_id=%s case_id=%s", run.id, case.id)
            self._record_error(session, run, case, type(exc).__name__)
            scores.append(0.0)

    @staticmethod
    def _record_error(session: AsyncSession, run: RagEvaluationRun, case: RagEvaluationCase, code: str) -> None:
        session.add(RagEvaluationResult(
            run_id=run.id, case_id=case.id, case_name=case.name, status="failed",
            score=0.0, passed=False, error_code=code[:128],
        ))
