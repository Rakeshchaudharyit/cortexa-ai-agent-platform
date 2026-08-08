from alembic.config import Config
from alembic.script import ScriptDirectory


def test_message_feedback_is_migration_head() -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("script_location", "backend/alembic")
    script = ScriptDirectory.from_config(config)
    assert set(script.get_heads()) == {"0019_eval_jobs"}
    assert script.get_revision("0014_message_feedback").down_revision == "0013_rag_evaluation_framework"
