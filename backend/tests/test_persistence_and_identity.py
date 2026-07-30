"""Auth persistence and database-identity protection tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import Settings
from app.db.health import check_database
from app.db.identity import check_database_identity
from app.db.session import dispose_engine, get_engine, get_session_factory, init_engine
from app.main import create_app
from app.models.user import User
from app.security.passwords import PasswordService
from app.services.auth import AuthService
from app.services.health import HealthService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_register_login_survives_new_session(
    settings: Settings,
    db_engine: None,
) -> None:
    """Register commits; a fresh session/engine path can still login."""
    _ = db_engine
    init_engine(settings)
    passwords = PasswordService.from_settings(settings)
    auth = AuthService.from_settings(settings)
    email = f"persist-{uuid.uuid4().hex[:10]}@example.com"
    password = "PersistentPass123!"

    factory = get_session_factory()
    async with factory() as session:
        result = await auth.register(
            session,
            email=email,
            password=password,
            full_name="Persist User",
        )
        user_id = result.response.user.id
        hash_before = (
            await session.execute(select(User.password_hash).where(User.id == user_id))
        ).scalar_one()
        await session.commit()

    # Dispose and recreate engine/session factory (restart-equivalent for DB pool).
    await dispose_engine()
    init_engine(settings)
    factory = get_session_factory()
    async with factory() as session:
        login = await auth.login(session, email=email, password=password)
        assert login.response.user.id == user_id
        hash_after = (
            await session.execute(select(User.password_hash).where(User.id == user_id))
        ).scalar_one()
        assert hash_after == hash_before
        assert passwords.verify_password(password, hash_after)

    await dispose_engine()
    init_engine(settings)


@pytest.mark.asyncio
async def test_database_identity_mismatch_fails_readiness(
    settings: Settings,
    db_engine: None,
) -> None:
    _ = db_engine
    engine = get_engine()
    ok, message = await check_database_identity(engine, settings)
    assert ok is True
    assert message is None

    wrong = settings.model_copy(update={"expected_database_identity": "wrong-identity-for-test"})
    bad_ok, bad_message = await check_database_identity(engine, wrong)
    assert bad_ok is False
    assert bad_message == "Database identity mismatch"

    app = create_app(wrong)
    with (
        patch(
            "app.services.health.check_database",
            new_callable=AsyncMock,
            return_value=(False, "Database identity mismatch"),
        ),
        patch(
            "app.services.health.check_redis",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
    ):
        app.state.health_service = HealthService(
            settings=wrong,
            engine=engine,
            redis=object(),  # type: ignore[arg-type]
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["checks"]["database"]["message"] == "Database identity mismatch"


@pytest.mark.asyncio
async def test_correct_identity_passes_check_database(
    settings: Settings,
    db_engine: None,
) -> None:
    _ = db_engine
    engine = get_engine()
    ok, message = await check_database(engine, settings)
    assert ok is True
    assert message is None


@pytest.mark.asyncio
async def test_application_metadata_seeded(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(text("SELECT key, value FROM application_metadata ORDER BY key"))
    ).fetchall()
    mapping = {row[0]: row[1] for row in rows}
    assert mapping["application_id"] == "cortexa-ai-agent-platform"
    assert mapping["database_identity"] == "cortexa-agent-test"
    assert mapping["created_by_project"] == "cortexa"


def test_makefile_down_does_not_use_volume_flag() -> None:
    from pathlib import Path

    candidates = (
        Path(__file__).resolve().parents[2] / "Makefile",  # host: repo/backend/tests
        Path(__file__).resolve().parents[1].parent / "Makefile",
        Path("/workspace/Makefile"),
        Path("/app/../Makefile"),
    )
    makefile = next((p for p in candidates if p.is_file()), None)
    if makefile is None:
        pytest.skip("Makefile not available in this test environment")
    text_body = makefile.read_text(encoding="utf-8")
    assert "\ndown:\n\tdocker compose down\n" in text_body
    assert "docker compose down -v" not in text_body


def test_no_test_uses_compose_down_v() -> None:
    from pathlib import Path

    here = Path(__file__).resolve()
    candidates = [here.parents[1], here.parents[2]]
    offenders: list[str] = []
    seen: set[Path] = set()
    for root in candidates:
        if root in seen or root == Path("/"):
            continue
        if not root.is_dir():
            continue
        # Only scan project-like trees.
        looks_like_project = (
            (root / "Makefile").is_file() or (root / "tests").is_dir() or (root / "app").is_dir()
        )
        if not looks_like_project:
            continue
        seen.add(root)
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(
                part in {".git", "node_modules", ".next", ".venv", "backups"} for part in path.parts
            ):
                continue
            allowed_suffixes = {".py", ".sh", ".md", ".yml", ".yaml"}
            if path.suffix not in allowed_suffixes and path.name != "Makefile":
                continue
            try:
                body = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError, PermissionError):
                continue
            needle = "docker compose down " + "-v"
            needle_alt = "docker-compose down " + "-v"
            if needle in body or needle_alt in body:
                if path.name in {
                    "reset_dev_database.sh",
                    "test_persistence_and_identity.py",
                }:
                    continue
                try:
                    offenders.append(str(path.relative_to(root)))
                except ValueError:
                    offenders.append(str(path))
    assert offenders == []
