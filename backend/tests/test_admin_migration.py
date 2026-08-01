"""Enterprise admin migration chain tests."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_enterprise_admin_migration_revision_chain() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    revisions = {rev.revision: rev for rev in script.walk_revisions()}
    assert "0009_enterprise_admin" in revisions
    rev = revisions["0009_enterprise_admin"]
    assert rev.down_revision == "0008_long_term_memory"
    assert "0010_admin_deletion_controls" in revisions
    rev10 = revisions["0010_admin_deletion_controls"]
    assert rev10.down_revision == "0009_enterprise_admin"
    heads = set(script.get_heads())
    assert heads == {"0010_admin_deletion_controls"}
