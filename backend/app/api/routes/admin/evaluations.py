"""Admin CRUD and execution endpoints for the RAG evaluation framework."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import func, select

from app.api.deps import CurrentAdminUser, DbSessionDep
from app.core.exceptions import AppError
from app.evaluations.schemas import (
    EvaluationCaseCreate,
    EvaluationCaseList,
    EvaluationCaseUpdate,
    EvaluationCaseView,
    EvaluationResultView,
    EvaluationRunDetail,
    EvaluationRunList,
    EvaluationRunView,
)
from app.evaluations.service import RagEvaluationService
from app.jobs.service import JobService
from app.models.job import BackgroundJob
from app.models.evaluation import RagEvaluationCase, RagEvaluationResult, RagEvaluationRun
from app.models.user import User

router = APIRouter()


def _case_view(item: RagEvaluationCase) -> EvaluationCaseView:
    return EvaluationCaseView(
        id=item.id,
        owner_user_id=item.owner_user_id,
        name=item.name,
        question=item.question,
        expected_answer=item.expected_answer,
        expected_keywords=list(item.expected_keywords_json),
        expected_document_ids=[uuid.UUID(value) for value in item.expected_document_ids_json],
        should_answer=item.should_answer,
        enabled=item.enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/evaluations/cases", response_model=EvaluationCaseList)
async def list_cases(_admin: CurrentAdminUser, session: DbSessionDep) -> EvaluationCaseList:
    items = list(
        (await session.scalars(select(RagEvaluationCase).order_by(RagEvaluationCase.created_at.desc()))).all()
    )
    return EvaluationCaseList(items=[_case_view(item) for item in items], total=len(items))


@router.post("/evaluations/cases", response_model=EvaluationCaseView, status_code=201)
async def create_case(
    body: EvaluationCaseCreate,
    admin: CurrentAdminUser,
    session: DbSessionDep,
) -> EvaluationCaseView:
    owner = await session.get(User, body.owner_user_id)
    if owner is None:
        raise AppError(
            code="evaluation_owner_not_found",
            message="Selected knowledge owner no longer exists",
            status_code=404,
        )
    item = RagEvaluationCase(
        owner_user_id=body.owner_user_id,
        created_by_user_id=admin.id,
        name=body.name.strip(),
        question=body.question.strip(),
        expected_answer=body.expected_answer.strip() if body.expected_answer else None,
        expected_keywords_json=sorted({value.strip() for value in body.expected_keywords if value.strip()}),
        expected_document_ids_json=[str(value) for value in body.expected_document_ids],
        should_answer=body.should_answer,
        enabled=body.enabled,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _case_view(item)


@router.patch("/evaluations/cases/{case_id}", response_model=EvaluationCaseView)
async def update_case(
    case_id: uuid.UUID,
    body: EvaluationCaseUpdate,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
) -> EvaluationCaseView:
    item = await session.get(RagEvaluationCase, case_id)
    if item is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates:
        item.name = updates["name"].strip()
    if "question" in updates:
        item.question = updates["question"].strip()
    if "expected_answer" in updates:
        value = updates["expected_answer"]
        item.expected_answer = value.strip() if value else None
    if "expected_keywords" in updates:
        item.expected_keywords_json = sorted({value.strip() for value in updates["expected_keywords"] if value.strip()})
    if "expected_document_ids" in updates:
        item.expected_document_ids_json = [str(value) for value in updates["expected_document_ids"]]
    if "should_answer" in updates:
        item.should_answer = updates["should_answer"]
    if "enabled" in updates:
        item.enabled = updates["enabled"]
    await session.commit()
    await session.refresh(item)
    return _case_view(item)


@router.delete(
    "/evaluations/cases/{case_id}",
    status_code=204,
    response_class=Response,
)
async def delete_case(
    case_id: uuid.UUID,
    _admin: CurrentAdminUser,
    session: DbSessionDep,
) -> Response:
    item = await session.get(RagEvaluationCase, case_id)
    if item is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    await session.delete(item)
    await session.commit()
    return Response(status_code=204)


@router.post("/evaluations/runs", response_model=EvaluationRunView, status_code=202)
async def run_evaluation(
    request: Request,
    admin: CurrentAdminUser,
    session: DbSessionDep,
) -> EvaluationRunView:
    rag_service = getattr(request.app.state, "rag_service", None)
    if rag_service is None:
        raise RuntimeError("RAG service is not configured")
    service = RagEvaluationService(rag_service=rag_service)
    run = await service.create_run(session, actor=admin)
    await session.flush()
    job_service = JobService(request.app.state.redis)
    job = await job_service.create_job(
        session, owner_user_id=admin.id, job_type="evaluation.run",
        payload={"source": "admin_evaluations", "run_id": str(run.id)},
        idempotency_key=f"evaluation-run:{run.id}", max_attempts=2,
    )
    run.background_job_id = job.id
    await session.commit()
    await session.refresh(run)
    return EvaluationRunView.model_validate(run)


@router.post("/evaluations/runs/{run_id}/export", status_code=202)
async def export_evaluation_run(
    run_id: uuid.UUID, request: Request, admin: CurrentAdminUser, session: DbSessionDep
) -> dict[str, str]:
    run = await session.get(RagEvaluationRun, run_id)
    if run is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if run.status != "completed":
        raise AppError(code="evaluation_not_complete", message="Evaluation must complete before export", status_code=409)
    job = await JobService(request.app.state.redis).create_job(
        session, owner_user_id=admin.id, job_type="evaluation.export",
        payload={"source": "admin_evaluations", "run_id": str(run_id)},
        idempotency_key=f"evaluation-export:{run_id}", max_attempts=2,
    )
    return {"job_id": str(job.id)}


@router.get("/evaluations/exports/{job_id}/download")
async def download_evaluation_export(
    job_id: uuid.UUID, request: Request, _admin: CurrentAdminUser, session: DbSessionDep
) -> FileResponse:
    job = await session.get(BackgroundJob, job_id)
    if job is None or job.job_type != "evaluation.export":
        raise AppError(code="not_found", message="Export job not found", status_code=404)
    if job.status != "succeeded" or not job.result_json:
        raise AppError(code="export_not_ready", message="Export is not ready", status_code=409)
    filename = str(job.result_json.get("filename") or "")
    if not filename or Path(filename).name != filename:
        raise AppError(code="export_invalid", message="Export file is unavailable", status_code=404)
    settings = request.app.state.settings
    path = Path(settings.document_storage_path) / "exports" / filename
    if not path.is_file():
        raise AppError(code="export_missing", message="Export file is unavailable", status_code=404)
    return FileResponse(path=path, media_type="text/csv", filename=f"rag-evaluation-{job.payload_json.get('run_id')}.csv")


@router.get("/evaluations/runs", response_model=EvaluationRunList)
async def list_runs(_admin: CurrentAdminUser, session: DbSessionDep) -> EvaluationRunList:
    items = list(
        (await session.scalars(select(RagEvaluationRun).order_by(RagEvaluationRun.created_at.desc()).limit(50))).all()
    )
    total = int((await session.scalar(select(func.count()).select_from(RagEvaluationRun))) or 0)
    return EvaluationRunList(items=[EvaluationRunView.model_validate(item) for item in items], total=total)


@router.get("/evaluations/runs/{run_id}", response_model=EvaluationRunDetail)
async def get_run(run_id: uuid.UUID, _admin: CurrentAdminUser, session: DbSessionDep) -> EvaluationRunDetail:
    run = await session.get(RagEvaluationRun, run_id)
    if run is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    results = list(
        (
            await session.scalars(
                select(RagEvaluationResult)
                .where(RagEvaluationResult.run_id == run_id)
                .order_by(RagEvaluationResult.created_at.asc())
            )
        ).all()
    )
    return EvaluationRunDetail(
        **EvaluationRunView.model_validate(run).model_dump(),
        results=[EvaluationResultView.model_validate(item) for item in results],
    )
