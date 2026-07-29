"""Shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    loc: list[str | int] = Field(default_factory=list)
    msg: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str


class FeatureFlags(BaseModel):
    ollama: bool = False
    auth: bool = False
    rag: bool = False
    memory: bool = False
    tools: bool = False
    voice: bool = False


class SystemInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
    api_version: str
    features: FeatureFlags
