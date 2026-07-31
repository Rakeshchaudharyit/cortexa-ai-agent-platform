"""Read-only memory tools — write actions require explicit user intent via chat."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.tools.base import BaseTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import ToolExecutionFailedError
from app.tools.schemas import ToolResultPayload


class MemoryListInput(BaseModel):
    limit: int = Field(default=10, ge=1, le=20)
    query: str | None = Field(default=None, max_length=200)


class MemorySearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)


def _memory_service_from_context(context: ToolExecutionContext) -> Any:
    service = context.extras.get("memory_service")
    if service is None:
        service = getattr(context.settings, "_memory_service", None) if context.settings else None
    return service


class MemoryListTool(BaseTool):
    name: ClassVar[str] = "memory_list"
    description: ClassVar[str] = (
        "List the current user's active long-term memories. "
        "Use when the user asks what you remember. Does not create or delete memories."
    )
    version: ClassVar[str] = "1.0.0"
    category: ClassVar[str] = "memory"
    input_model: ClassVar[type[BaseModel]] = MemoryListInput
    timeout_seconds: ClassVar[int] = 10

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        assert isinstance(arguments, MemoryListInput)
        memory_service = context.extras.get("memory_service")
        if memory_service is None:
            raise ToolExecutionFailedError("Memory service unavailable")
        from app.models.user import User

        user = await context.session.get(User, context.user_id)
        if user is None:
            raise ToolExecutionFailedError("User not found")
        items = await memory_service.list_for_prompt(
            context.session,
            user,
            query=arguments.query,
            limit=arguments.limit,
        )
        return ToolResultPayload(
            success=True,
            data={
                "count": len(items),
                "memories": [
                    {
                        "title": m.title,
                        "category": m.category.value,
                        "content": m.content,
                    }
                    for m in items
                ],
            },
        )


class MemorySearchTool(BaseTool):
    name: ClassVar[str] = "memory_search"
    description: ClassVar[str] = (
        "Search the current user's active long-term memories by keyword. "
        "Read-only; does not create or delete memories."
    )
    version: ClassVar[str] = "1.0.0"
    category: ClassVar[str] = "memory"
    input_model: ClassVar[type[BaseModel]] = MemorySearchInput
    timeout_seconds: ClassVar[int] = 10

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        assert isinstance(arguments, MemorySearchInput)
        memory_service = context.extras.get("memory_service")
        if memory_service is None:
            raise ToolExecutionFailedError("Memory service unavailable")
        from app.models.user import User

        user = await context.session.get(User, context.user_id)
        if user is None:
            raise ToolExecutionFailedError("User not found")
        items = await memory_service.list_for_prompt(
            context.session,
            user,
            query=arguments.query,
            limit=arguments.limit,
        )
        return ToolResultPayload(
            success=True,
            data={
                "count": len(items),
                "memories": [
                    {
                        "title": m.title,
                        "category": m.category.value,
                        "content": m.content,
                    }
                    for m in items
                ],
            },
        )
