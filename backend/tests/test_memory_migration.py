"""Alembic migration coverage for Phase 7 long-term memory."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_long_term_memory_migration_revision_chain() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    revisions = {rev.revision: rev for rev in script.walk_revisions()}
    assert "0008_long_term_memory" in revisions
    rev = revisions["0008_long_term_memory"]
    assert rev.down_revision == "0007_agent_tools"
    heads = set(script.get_heads())
    assert heads == {"0010_admin_deletion_controls"}
    assert revisions["0009_enterprise_admin"].down_revision == "0008_long_term_memory"
    assert revisions["0010_admin_deletion_controls"].down_revision == "0009_enterprise_admin"
