from alembic.config import Config
from alembic.script import ScriptDirectory


def test_knowledge_lifecycle_is_migration_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert set(script.get_heads()) == {"0019_eval_jobs"}
    assert script.get_revision("0016_doc_lifecycle").down_revision == "0015_knowledge_mgmt"
    assert script.get_revision("0015_knowledge_mgmt").down_revision == "0014_message_feedback"


def test_alembic_revision_fits_default_version_column() -> None:
    assert len("0016_doc_lifecycle") <= 32
