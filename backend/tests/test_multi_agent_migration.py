"""Alembic migration coverage for Phase 9 multi-agent orchestration."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_multi_agent_orchestration_migration_revision_chain() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    revisions = {rev.revision: rev for rev in script.walk_revisions()}
    assert "0011_multi_agent_orchestration" in revisions
    rev = revisions["0011_multi_agent_orchestration"]
    assert rev.down_revision == "0010_admin_deletion_controls"
    heads = set(script.get_heads())
    assert heads == {"0011_multi_agent_orchestration"}
