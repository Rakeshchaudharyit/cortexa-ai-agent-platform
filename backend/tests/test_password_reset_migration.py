"""Migration / ORM alignment tests for password_reset_tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.test_safety import assert_safe_test_session
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_password_reset_table_indexes_and_cascade(
    db_session: AsyncSession,
) -> None:
    await assert_safe_test_session(db_session)
    connection = await db_session.connection()

    def _inspect(sync_conn):  # type: ignore[no-untyped-def]
        inspector = inspect(sync_conn)
        assert "password_reset_tokens" in inspector.get_table_names()
        columns = {col["name"] for col in inspector.get_columns("password_reset_tokens")}
        expected = {
            "id",
            "user_id",
            "token_hash",
            "expires_at",
            "used_at",
            "revoked_at",
            "requested_ip_hash",
            "user_agent_hash",
            "created_at",
        }
        assert expected <= columns
        indexes = inspector.get_indexes("password_reset_tokens")
        assert any("user_id" in idx["column_names"] for idx in indexes)
        assert any("created_at" in idx["column_names"] for idx in indexes)
        uniques = inspector.get_unique_constraints("password_reset_tokens")
        unique_cols = {tuple(u["column_names"]) for u in uniques}
        assert ("token_hash",) in unique_cols or any(
            idx.get("unique") and idx["column_names"] == ["token_hash"] for idx in indexes
        )
        fks = inspector.get_foreign_keys("password_reset_tokens")
        assert any(fk["referred_table"] == "users" for fk in fks)

    await connection.run_sync(_inspect)

    user = User(
        email="cascade-reset@example.com",
        password_hash="$argon2id$v=19$m=8$test",
        full_name="Cascade",
    )
    db_session.add(user)
    await db_session.flush()
    token = PasswordResetToken(
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(token)
    await db_session.commit()

    await db_session.execute(text("DELETE FROM users WHERE email = 'cascade-reset@example.com'"))
    await db_session.commit()
    remaining = await db_session.execute(
        text("SELECT count(*) FROM password_reset_tokens WHERE token_hash = :h"),
        {"h": "a" * 64},
    )
    assert remaining.scalar_one() == 0


def test_migration_chain_includes_password_reset() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    revisions = {rev.revision for rev in script.walk_revisions()}
    assert "0005_password_reset" in revisions
    assert "0006_database_identity" in revisions
    assert "0004_phase5_conversations" in revisions
    head = script.get_current_head()
    assert head == "0006_database_identity"


def test_orm_model_fields_align() -> None:
    columns = PasswordResetToken.__table__.columns
    assert "token_hash" in columns
    assert columns["token_hash"].type.length == 64
    assert columns["user_id"].nullable is False
    assert User.password_reset_tokens.property.mapper.class_ is PasswordResetToken
