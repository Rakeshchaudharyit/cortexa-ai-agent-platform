from app.jobs.service import ALLOWED_JOB_TYPES


def test_phase_12_3_job_types_are_registered() -> None:
    assert "evaluation.run" in ALLOWED_JOB_TYPES
    assert "evaluation.export" in ALLOWED_JOB_TYPES


def test_phase_12_3_does_not_remove_existing_job_types() -> None:
    assert {"demo.validation", "document.ingestion", "document.reindex"}.issubset(ALLOWED_JOB_TYPES)


def test_phase_12_3_migration_chain() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert set(script.get_heads()) == {"0019_eval_jobs"}
    assert script.get_revision("0019_eval_jobs").down_revision == "0018_document_jobs"
