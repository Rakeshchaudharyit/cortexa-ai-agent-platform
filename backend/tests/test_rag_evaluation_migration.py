from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_rag_evaluation_migration_is_single_head():
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert set(script.get_heads()) == {"0019_eval_jobs"}
    assert script.get_revision("0013_rag_evaluation_framework").down_revision == "0012_agent_run_telemetry"
