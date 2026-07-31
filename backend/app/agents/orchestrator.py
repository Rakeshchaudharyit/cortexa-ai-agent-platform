"""Multi-step agent orchestrator: LLM ↔ tools loop with streaming events."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import merge_system_prompt
from app.agents.schemas import (
    AgentRunConfig,
    AgentRunResult,
    tool_calls_from_provider,
    tool_result_content,
    tool_specs_to_provider,
)
from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.llm.schemas import (
    ChatMessage,
    GenerateRequest,
    MessageRole,
    StreamEvent,
    StreamEventType,
    ToolCallRequest,
)
from app.models.enums import UserRole
from app.models.user import User
from app.services.llm import LLMService
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

logger = logging.getLogger("cortexa.agents.orchestrator")


class AgentOrchestrator:
    """Coordinate tool-aware generation without coupling to a specific LLM vendor."""

    def __init__(
        self,
        *,
        settings: Settings,
        llm_service: LLMService,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
    ) -> None:
        self.settings = settings
        self.llm_service = llm_service
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor

    def _provider_tools(self, role: UserRole) -> list[Any]:
        specs = self.tool_registry.provider_schemas(role=role)
        return tool_specs_to_provider(specs)

    async def run(
        self,
        *,
        session: AsyncSession,
        user: User,
        messages: list[ChatMessage],
        system: str | None,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        allowed_document_ids: list[uuid.UUID] | None,
        config: AgentRunConfig | None = None,
    ) -> AgentRunResult:
        """Non-streaming agent loop. Returns the final assistant content."""
        events: list[StreamEvent] = []
        async for event in self.stream(
            session=session,
            user=user,
            messages=messages,
            system=system,
            conversation_id=conversation_id,
            message_id=message_id,
            allowed_document_ids=allowed_document_ids,
            config=config,
        ):
            events.append(event)

        content = ""
        tool_ids: list[str] = []
        iterations = 0
        finish_reason = None
        provider = None
        model = None
        usage: dict[str, Any] = {}
        for event in events:
            if event.event == StreamEventType.delta:
                content += str(event.data.get("content") or "")
            elif event.event == StreamEventType.tool_execution_started:
                eid = event.data.get("execution_id")
                if eid:
                    tool_ids.append(str(eid))
            elif event.event == StreamEventType.agent_completed:
                iterations = int(event.data.get("iterations") or 0)
                finish_reason = event.data.get("finish_reason")
                provider = event.data.get("provider")
                model = event.data.get("model")
                usage = event.data.get("usage") or {}
            elif event.event == StreamEventType.assistant_completed:
                if event.data.get("content"):
                    content = str(event.data["content"])

        return AgentRunResult(
            content=content,
            tool_execution_ids=tool_ids,
            iterations=iterations,
            finish_reason=finish_reason,
            provider=provider,
            model=model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            grounded_from_tools=bool(tool_ids),
        )

    async def stream(
        self,
        *,
        session: AsyncSession,
        user: User,
        messages: list[ChatMessage],
        system: str | None,
        conversation_id: uuid.UUID | None,
        message_id: uuid.UUID | None,
        allowed_document_ids: list[uuid.UUID] | None,
        config: AgentRunConfig | None = None,
    ) -> AsyncIterator[StreamEvent]:
        cfg = config or AgentRunConfig(
            max_iterations=self.settings.agent_max_tool_iterations,
        )
        max_iterations = min(cfg.max_iterations, self.settings.agent_max_tool_iterations)
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()

        yield StreamEvent(
            event=StreamEventType.agent_started,
            data={
                "conversation_id": str(conversation_id) if conversation_id else None,
                "message_id": str(message_id) if message_id else None,
                "max_iterations": max_iterations,
            },
        )
        logger.info(
            "agent_started user_id=%s conversation_id=%s message_id=%s "
            "max_iterations=%s request_id=%s",
            user.id,
            conversation_id,
            message_id,
            max_iterations,
            request_id,
        )

        working = list(messages)
        system_prompt = merge_system_prompt(system, tools_enabled=True)
        tools = self._provider_tools(user.role)
        tool_execution_ids: list[str] = []
        active_stack: list[str] = []
        iterations = 0
        final_content = ""
        provider_name = self.llm_service.provider.name
        model_name = self.llm_service.provider.default_model
        usage_acc: dict[str, int | None] = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
        finish_reason: str | None = None

        try:
            while iterations < max_iterations:
                iterations += 1
                generate_request = GenerateRequest(
                    messages=working,
                    system=system_prompt,
                    temperature=cfg.temperature,
                    max_tokens=cfg.max_tokens,
                    tools=tools or None,
                    tool_choice="auto" if tools else None,
                )
                generation = await self.llm_service.generate(generate_request)
                provider_name = generation.provider
                model_name = generation.model
                if generation.usage:
                    usage_acc["prompt_tokens"] = generation.usage.prompt_tokens
                    usage_acc["completion_tokens"] = generation.usage.completion_tokens
                    usage_acc["total_tokens"] = generation.usage.total_tokens

                tool_calls = tool_calls_from_provider(generation.tool_calls)
                if not tool_calls:
                    final_content = generation.content or ""
                    finish_reason = generation.finish_reason or "stop"
                    # Stream final text as compatible delta tokens for the UI.
                    if final_content:
                        yield StreamEvent(
                            event=StreamEventType.delta,
                            data={"content": final_content},
                        )
                        yield StreamEvent(
                            event=StreamEventType.assistant_token,
                            data={"content": final_content},
                        )
                    yield StreamEvent(
                        event=StreamEventType.assistant_completed,
                        data={"content": final_content},
                    )
                    break

                # Persist assistant tool-call turn in the working transcript.
                working.append(
                    ChatMessage(
                        role=MessageRole.assistant,
                        content=generation.content or "",
                        tool_calls=[
                            ToolCallRequest(
                                id=call.id,
                                name=call.name,
                                arguments=call.arguments,
                            )
                            for call in tool_calls
                        ],
                    )
                )

                for call in tool_calls:
                    logger.info(
                        "tool_requested tool=%s iteration=%s user_id=%s "
                        "conversation_id=%s request_id=%s",
                        call.name,
                        iterations,
                        user.id,
                        conversation_id,
                        request_id,
                    )
                    yield StreamEvent(
                        event=StreamEventType.tool_call_started,
                        data={
                            "tool_call_id": call.id,
                            "tool_name": call.name,
                            "iteration": iterations,
                        },
                    )
                    yield StreamEvent(
                        event=StreamEventType.tool_call_arguments,
                        data={
                            "tool_call_id": call.id,
                            "tool_name": call.name,
                            "arguments": call.arguments,
                        },
                    )

                    # Hallucinated / unauthorized tool names are untrusted input.
                    if not self.tool_registry.has(call.name):
                        error_msg = f"Tool '{call.name}' is not available"
                        yield StreamEvent(
                            event=StreamEventType.tool_execution_failed,
                            data={
                                "tool_call_id": call.id,
                                "tool_name": call.name,
                                "error_code": "tool_not_found",
                                "error_message": error_msg,
                            },
                        )
                        working.append(
                            ChatMessage(
                                role=MessageRole.tool,
                                tool_call_id=call.id,
                                name=call.name,
                                content=tool_result_content(
                                    None,
                                    success=False,
                                    error=error_msg,
                                ),
                            )
                        )
                        continue

                    record, result = await self.tool_executor.execute(
                        session=session,
                        tool_name=call.name,
                        arguments=call.arguments,
                        user_id=user.id,
                        user_role=user.role,
                        conversation_id=conversation_id,
                        message_id=message_id,
                        request_id=request_id,
                        correlation_id=request_id,
                        allowed_document_ids=allowed_document_ids,
                        active_tool_stack=active_stack,
                        persist=True,
                    )
                    if record is not None:
                        tool_execution_ids.append(str(record.id))
                        yield StreamEvent(
                            event=StreamEventType.tool_execution_started,
                            data={
                                "execution_id": str(record.id),
                                "tool_call_id": call.id,
                                "tool_name": call.name,
                            },
                        )
                        await session.flush()

                    if result.success:
                        yield StreamEvent(
                            event=StreamEventType.tool_execution_succeeded,
                            data={
                                "execution_id": str(record.id) if record else None,
                                "tool_call_id": call.id,
                                "tool_name": call.name,
                                "result": result.data if result.expose_to_llm else {"ok": True},
                            },
                        )
                        content = tool_result_content(
                            result.data if result.expose_to_llm else {"ok": True},
                            success=True,
                            error=None,
                        )
                    else:
                        yield StreamEvent(
                            event=StreamEventType.tool_execution_failed,
                            data={
                                "execution_id": str(record.id) if record else None,
                                "tool_call_id": call.id,
                                "tool_name": call.name,
                                "error_code": result.error_code,
                                "error_message": result.error_message,
                            },
                        )
                        content = tool_result_content(
                            None,
                            success=False,
                            error=result.error_message,
                        )

                    working.append(
                        ChatMessage(
                            role=MessageRole.tool,
                            tool_call_id=call.id,
                            name=call.name,
                            content=content,
                        )
                    )
            else:
                # Max iterations reached without a plain-text finish.
                finish_reason = "max_tool_iterations"
                if not final_content:
                    final_content = (
                        "I reached the maximum number of tool steps for this turn. "
                        "Please refine your request or continue in a new message."
                    )
                    yield StreamEvent(
                        event=StreamEventType.delta,
                        data={"content": final_content},
                    )
                    yield StreamEvent(
                        event=StreamEventType.assistant_completed,
                        data={"content": final_content},
                    )

            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            yield StreamEvent(
                event=StreamEventType.agent_completed,
                data={
                    "iterations": iterations,
                    "tool_execution_ids": tool_execution_ids,
                    "finish_reason": finish_reason,
                    "provider": provider_name,
                    "model": model_name,
                    "usage": usage_acc,
                    "latency_ms": latency_ms,
                },
            )
            logger.info(
                "agent_completed user_id=%s conversation_id=%s iterations=%s "
                "tools=%s latency_ms=%s request_id=%s",
                user.id,
                conversation_id,
                iterations,
                len(tool_execution_ids),
                latency_ms,
                request_id,
            )
        except Exception as exc:
            from app.core.exceptions import AppError

            code = exc.code if isinstance(exc, AppError) else "agent_failed"
            message = exc.message if isinstance(exc, AppError) else "Agent orchestration failed"
            if not isinstance(exc, AppError):
                logger.exception(
                    "agent_failed user_id=%s conversation_id=%s request_id=%s",
                    user.id,
                    conversation_id,
                    request_id,
                )
            yield StreamEvent(
                event=StreamEventType.agent_failed,
                data={"error": {"code": code, "message": message}},
            )
            yield StreamEvent(
                event=StreamEventType.error,
                data={"error": {"code": code, "message": message}},
            )
