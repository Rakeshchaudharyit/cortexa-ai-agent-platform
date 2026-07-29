"""Embedding schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EmbeddingStatus(str, Enum):
    ready = "ready"
    model_unavailable = "model_unavailable"
    provider_unavailable = "provider_unavailable"
    misconfigured = "misconfigured"


class EmbeddingHealthResult(BaseModel):
    provider: str
    model: str
    provider_reachable: bool
    model_available: bool
    configured_dimension: int
    status: EmbeddingStatus
    message: str


class EmbeddingVector(BaseModel):
    values: list[float] = Field(min_length=1)
    dimension: int
