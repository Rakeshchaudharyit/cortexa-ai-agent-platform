from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).parents[2]
BACKEND = ROOT / "backend"


def test_document_job_migration_is_head() -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert set(script.get_heads()) == {"0019_eval_jobs"}
    assert script.get_revision("0018_document_jobs").down_revision == "0017_job_queue"


def test_document_upload_queues_in_deployable_environments() -> None:
    source = (BACKEND / "app" / "api" / "routes" / "documents.py").read_text()
    assert "create_pending_upload" in source
    assert 'job_type="document.ingestion"' in source
    assert 'job_type="document.reindex"' in source
    assert "settings.app_env == \"test\"" in source


def test_index_swap_occurs_after_embeddings_are_complete() -> None:
    source = (BACKEND / "app" / "jobs" / "document_ingestion.py").read_text()
    embed_position = source.index("embed_batch")
    delete_position = source.index("delete(DocumentChunk)")
    assert embed_position < delete_position
    assert "with_for_update" in source
    assert "version_activated" in source


def test_document_page_polls_active_jobs() -> None:
    source = (ROOT / "frontend" / "components" / "documents" / "DocumentPanel.tsx").read_text()
    assert "hasActiveJobs" in source
    assert "job_progress_percent" in source
    assert "window.setInterval" in source
