"""Health and readiness response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "backend"
    version: str
    environment: str


class DependencyCheck(BaseModel):
    status: Literal["ok", "error"]
    message: str | None = None


class ReadinessChecks(BaseModel):
    database: DependencyCheck
    redis: DependencyCheck


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks = Field(...)
