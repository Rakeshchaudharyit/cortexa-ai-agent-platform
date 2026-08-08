from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_job_queue_is_migration_head() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert set(script.get_heads()) == {"0019_eval_jobs"}
    assert script.get_revision("0017_job_queue").down_revision == "0016_doc_lifecycle"


def test_worker_service_is_declared() -> None:
    compose = (Path(__file__).parents[2] / "docker-compose.yml").read_text()
    assert "  worker:" in compose
    assert 'command: ["python", "-m", "app.jobs.worker"]' in compose
    assert "cortexa:jobs:worker:heartbeat" in compose


def test_worker_never_executes_request_scoped_sessions() -> None:
    worker = (Path(__file__).parents[1] / "app" / "jobs" / "worker.py").read_text()
    assert "get_session_factory" in worker
    assert "Depends(" not in worker


def test_document_job_migration_follows_queue_foundation() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("backend/alembic.ini"))
    assert script.get_revision("0018_document_jobs").down_revision == "0017_job_queue"
