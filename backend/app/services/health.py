"""Health and readiness service — orchestrates dependency checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.health import check_database
from app.providers.redis import check_redis
from app.schemas.common import FeatureFlags, SystemInfoResponse
from app.schemas.health import (
    DependencyCheck,
    HealthResponse,
    ReadinessChecks,
    ReadinessResponse,
)


@dataclass
class HealthService:
    """Application health / readiness / system info. No infrastructure in routes."""

    settings: Settings
    engine: AsyncEngine | None = None
    redis: Redis[Any] | None = None

    def liveness(self) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="backend",
            version=self.settings.app_version,
            environment=self.settings.app_env,
        )

    async def readiness(self) -> tuple[ReadinessResponse, int]:
        """Infra readiness: DB connectivity, migration head, required tables, Redis.

        Sanitized failure messages only — never connection strings or hostnames.
        Schema/migration failures surface under the database check so clients
        keep a stable readiness contract (database + redis).
        """
        db_ok = False
        db_message: str | None = "Database unavailable"
        redis_ok = False
        redis_message: str | None = "Redis unavailable"

        if self.engine is not None:
            db_ok, db_message = await check_database(self.engine, self.settings)
        if self.redis is not None:
            redis_ok, redis_message = await check_redis(self.redis)

        checks = ReadinessChecks(
            database=DependencyCheck(
                status="ok" if db_ok else "error",
                message=None if db_ok else (db_message or "Database unavailable"),
            ),
            redis=DependencyCheck(
                status="ok" if redis_ok else "error",
                message=None if redis_ok else (redis_message or "Redis unavailable"),
            ),
        )
        if db_ok and redis_ok:
            return ReadinessResponse(status="ready", checks=checks), 200
        return ReadinessResponse(status="not_ready", checks=checks), 503

    def system_info(self) -> SystemInfoResponse:
        api_version = self.settings.api_prefix.lstrip("/").split("/")[-1] or "v1"
        return SystemInfoResponse(
            name=self.settings.app_name,
            version=self.settings.app_version,
            environment=self.settings.app_env,
            api_version=api_version,
            features=FeatureFlags(
                ollama=True,
                auth=True,
                rag=True,
                memory=True,
                tools=self.settings.agent_tools_enabled,
                voice=False,
                password_reset_dev_notice=(
                    self.settings.password_reset_dev_notice_enabled
                    and not self.settings.is_production
                ),
            ),
        )
