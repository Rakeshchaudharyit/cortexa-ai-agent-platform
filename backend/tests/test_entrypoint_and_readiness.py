"""Entrypoint migration behavior and schema readiness regression tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import Settings
from app.db.health import (
    REQUIRED_CONVERSATION_TABLES,
    check_database,
    check_required_tables,
)
from app.db.session import get_engine, init_engine
from app.main import create_app
from app.services.health import HealthService
from httpx import ASGITransport, AsyncClient

ENTRYPOINT_CANDIDATES = (
    Path("/docker-entrypoint.sh"),
    Path(__file__).resolve().parents[1] / "docker-entrypoint.sh",
)


def _entrypoint_path() -> Path:
    for candidate in ENTRYPOINT_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "docker-entrypoint.sh not found in image (/docker-entrypoint.sh) " "or backend package tree"
    )


def test_entrypoint_runs_alembic_upgrade_before_exec() -> None:
    text_body = _entrypoint_path().read_text(encoding="utf-8")
    assert "set -eu" in text_body
    assert "alembic upgrade head" in text_body
    # Migrations must run before the final exec of the app command.
    alembic_pos = text_body.rfind("alembic upgrade head")
    exec_pos = text_body.rfind("exec ")
    assert alembic_pos != -1
    assert exec_pos != -1
    assert alembic_pos < exec_pos


def test_entrypoint_migration_failure_aborts_startup(tmp_path: Path) -> None:
    """Simulate alembic failure — entrypoint must exit non-zero before app start.

    Uses a minimal non-root replica of the production entrypoint contract
    (`set -eu`, `alembic upgrade head`, then `exec`) so PATH overrides are
    reliable inside Docker (root + runuser would reset PATH).
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    alembic = fake_bin / "alembic"
    alembic.write_text(
        "#!/bin/sh\necho 'simulated migration failure' >&2\nexit 42\n",
        encoding="utf-8",
    )
    alembic.chmod(0o755)
    marker = tmp_path / "uvicorn-started"
    uvicorn = fake_bin / "uvicorn"
    uvicorn.write_text(
        f"#!/bin/sh\ntouch '{marker}'\nexit 0\n",
        encoding="utf-8",
    )
    uvicorn.chmod(0o755)

    entrypoint = tmp_path / "entrypoint.sh"
    # Mirror backend/docker-entrypoint.sh non-root migration + exec contract.
    entrypoint.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'echo "cortexa: applying database migrations (alembic upgrade head)"\n'
        "alembic upgrade head\n"
        'echo "cortexa: migrations applied successfully"\n'
        'exec "$@"\n',
        encoding="utf-8",
    )
    entrypoint.chmod(0o755)

    # Production entrypoint must still contain the same hard-fail contract.
    production = _entrypoint_path().read_text(encoding="utf-8")
    assert "set -eu" in production
    assert "alembic upgrade head" in production

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["DOCUMENT_STORAGE_PATH"] = str(tmp_path / "storage")

    result = subprocess.run(
        ["/bin/sh", str(entrypoint), "uvicorn", "app.main:app"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )
    assert result.returncode != 0
    assert not marker.exists()
    assert "simulated migration failure" in (result.stderr + result.stdout)


@pytest.mark.asyncio
async def test_readiness_succeeds_at_0004_head(
    settings: Settings,
    db_engine: None,
) -> None:
    _ = db_engine
    engine = get_engine()
    app = create_app(settings)
    with patch("app.services.health.check_redis", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = (True, None)
        app.state.health_service = HealthService(
            settings=settings,
            engine=engine,
            redis=object(),  # type: ignore[arg-type]
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for path in ("/ready", "/health/ready"):
                response = await client.get(path)
                assert response.status_code == 200, response.text
                payload = response.json()
                assert payload["status"] == "ready"
                assert payload["checks"]["database"]["status"] == "ok"
                assert payload["checks"]["database"].get("message") is None


@pytest.mark.asyncio
async def test_readiness_fails_when_conversations_table_missing(
    settings: Settings,
    db_engine: None,
) -> None:
    _ = db_engine
    engine = get_engine()
    ok, _message = await check_required_tables(engine)
    assert ok is True

    with patch(
        "app.db.health.check_required_tables",
        new_callable=AsyncMock,
        return_value=(False, "Database schema incomplete"),
    ):
        with patch(
            "app.db.health.check_migrations",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            db_ok, db_message = await check_database(engine, settings)
    assert db_ok is False
    assert db_message == "Database schema incomplete"

    app = create_app(settings)
    with (
        patch(
            "app.services.health.check_database",
            new_callable=AsyncMock,
            return_value=(False, "Database schema incomplete"),
        ),
        patch(
            "app.services.health.check_redis",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
    ):
        app.state.health_service = HealthService(
            settings=settings,
            engine=engine,
            redis=object(),  # type: ignore[arg-type]
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["status"] == "error"
    assert payload["checks"]["database"]["message"] == "Database schema incomplete"
    body = response.text.lower()
    assert "localhost" not in body
    assert "traceback" not in body


@pytest.mark.asyncio
async def test_check_database_requires_phase5_tables(
    settings: Settings,
    db_engine: None,
) -> None:
    _ = db_engine
    init_engine(settings)
    engine = get_engine()
    ok, message = await check_database(engine, settings)
    assert ok is True
    assert message is None
    assert "conversations" in REQUIRED_CONVERSATION_TABLES


@pytest.mark.asyncio
async def test_liveness_aliases_remain_process_only(
    settings: Settings,
    client: AsyncClient,
) -> None:
    _ = settings
    for path in ("/health", "/health/live"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_startup_applies_migration_head_documented_in_entrypoint() -> None:
    """Contract: container startup applies head before the app listens."""
    body = _entrypoint_path().read_text(encoding="utf-8")
    assert "alembic upgrade head" in body
    # Root and non-root paths both invoke alembic before exec.
    assert body.count("alembic upgrade head") >= 2
