"""Typed base contract for agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from app.models.enums import UserRole
from app.tools.context import ToolExecutionContext
from app.tools.schemas import ToolResultPayload, ToolSpec


class BaseTool(ABC):
    """Server-side tool definition. Arguments are always validated via Pydantic."""

    name: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    category: ClassVar[str] = "general"
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel] | None] = None
    required_roles: ClassVar[frozenset[UserRole]] = frozenset({UserRole.user, UserRole.admin})
    timeout_seconds: ClassVar[int] = 30
    requires_confirmation: ClassVar[bool] = False
    enabled: ClassVar[bool] = True
    expose_result_to_llm: ClassVar[bool] = True

    def is_allowed_for_role(self, role: UserRole) -> bool:
        return role in self.required_roles

    def to_spec(self) -> ToolSpec:
        schema = self.input_model.model_json_schema()
        # Strip noisy schema metadata for provider payloads.
        parameters = {
            key: value
            for key, value in schema.items()
            if key not in {"title", "$defs", "definitions"}
        }
        if "$defs" in schema or "definitions" in schema:
            # Keep defs when referenced by $ref — provider needs them.
            if "$defs" in schema:
                parameters["$defs"] = schema["$defs"]
            if "definitions" in schema:
                parameters["definitions"] = schema["definitions"]
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=parameters,
            version=self.version,
            category=self.category,
        )

    def validate_arguments(self, raw: dict[str, object]) -> BaseModel:
        return self.input_model.model_validate(raw)

    @abstractmethod
    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        """Execute with validated arguments. Must not raise raw secrets."""
