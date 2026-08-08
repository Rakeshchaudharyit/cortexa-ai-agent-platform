"""Regression coverage for Phase 12.2.1 finalization diagnostics."""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_document_finalization_has_explicit_flush_checkpoints() -> None:
    source = (BACKEND / "app" / "jobs" / "document_ingestion.py").read_text()
    assert 'stage="chunks"' not in source  # stage is supplied positionally to the safe error
    assert 'DocumentFinalizationError("chunks")' in source
    assert 'DocumentFinalizationError("document")' in source
    assert 'DocumentFinalizationError("activation")' in source
    assert 'DocumentFinalizationError("event")' in source
    assert source.count("await session.flush()") >= 4


def test_embedding_vectors_are_validated_before_database_finalization() -> None:
    source = (BACKEND / "app" / "jobs" / "document_ingestion.py").read_text()
    assert "_validate_embeddings(embeddings" in source
    assert "EMBEDDING_DIMENSION" in source
    assert "math.isfinite" in source


def test_worker_persists_safe_specific_error_details() -> None:
    source = (BACKEND / "app" / "jobs" / "worker.py").read_text()
    assert "_safe_exception_fields" in source
    assert "error_code = error_code" in source
    assert "job.error_message = error_message" in source
    assert "job_execution_failed job_id=%s job_type=%s error_code=%s error_message=%s" in source
