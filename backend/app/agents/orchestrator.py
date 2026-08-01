"""Multi-step agent orchestrator: LLM ↔ tools loop with streaming events."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
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
from app.agents.tool_selection import KNOWN_TOOL_NAMES, filter_provider_tool_names
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

CancelCheck = Callable[[], Awaitable[bool] | bool]


def _progressive_chunks(text: str, *, max_chunk: int = 24) -> list[str]:
    """Split final text into small chunks for progressive SSE emission."""
    if not text:
        return []
    if len(text) <= max_chunk:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chunk:
            chunks.append(remaining)
            break
        split_at = remaining.rfind(" ", 0, max_chunk + 1)
        if split_at <= 0:
            split_at = max_chunk
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    return chunks


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

    def _provider_tools_for_names(
        self,
        role: UserRole,
        selected_names: list[str],
    ) -> list[Any]:
        allowed = filter_provider_tool_names(
            candidate_names=selected_names,
            registered_tool_names=frozenset(
                tool.name for tool in self.tool_registry.list_enabled(role=role)
            ),
        )
        # Extra hard gate against unknown names.
        allowed = [name for name in allowed if name in KNOWN_TOOL_NAMES]
        if not allowed:
            return []
        specs = [
            tool.to_spec()
            for tool in self.tool_registry.list_enabled(role=role)
            if tool.name in allowed
        ]
        return tool_specs_to_provider(specs)

    async def _cancelled(self, cancel_check: CancelCheck | None) -> bool:
        if cancel_check is None:
            return False
        result = cancel_check()
        if asyncio.iscoroutine(result):
            return bool(await result)
        return bool(result)

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
        cancel_check: CancelCheck | None = None,
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
            cancel_check=cancel_check,
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

    async def _stream_final_answer(
        self,
        *,
        messages: list[ChatMessage],
        system_prompt: str,
        temperature: float | None,
        max_tokens: int | None,
        cancel_check: CancelCheck | None,
    ) -> AsyncIterator[tuple[str, StreamEvent | None, dict[str, Any]]]:
        """Real provider stream without tool schemas. Yields (delta, event, meta)."""
        generate_request = GenerateRequest(
            messages=messages,
            system=system_prompt or None,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=None,
            tool_choice=None,
        )
        meta: dict[str, Any] = {}
        async for event in self.llm_service.stream(generate_request):
            if await self._cancelled(cancel_check):
                raise asyncio.CancelledError()
            if event.event == StreamEventType.delta:
                chunk = str(event.data.get("content") or "")
                if chunk:
                    # Canonical assistant text event is `delta`. Do not also emit
                    # `assistant_token` with the same content — clients that append
                    # both produce duplicated answers.
                    yield (
                        chunk,
                        StreamEvent(
                            event=StreamEventType.delta,
                            data={"content": chunk},
                        ),
                        meta,
                    )
            elif event.event == StreamEventType.complete:
                meta = event.data
            elif event.event == StreamEventType.error:
                yield "", event, meta
                return
            elif event.event == StreamEventType.start:
                continue

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
        cancel_check: CancelCheck | None = None,
    ) -> AsyncIterator[StreamEvent]:
        cfg = config or AgentRunConfig(
            max_iterations=self.settings.agent_max_tool_iterations,
        )
        max_iterations = min(cfg.max_iterations, self.settings.agent_max_tool_iterations)
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()
        first_token_at: float | None = None
        generated_token_count = 0
        cancellation_status = "none"
        provider_streaming = False

        selected_names = filter_provider_tool_names(
            candidate_names=list(cfg.selected_tool_names),
            registered_tool_names=frozenset(
                tool.name for tool in self.tool_registry.list_enabled(role=user.role)
            ),
        )
        tools = self._provider_tools_for_names(user.role, selected_names)
        tools_enabled = bool(tools)

        approx_prompt_chars = sum(len(m.content or "") for m in messages) + len(system or "")
        prompt_message_count = len(messages) + (1 if system else 0)

        yield StreamEvent(
            event=StreamEventType.agent_started,
            data={
                "conversation_id": str(conversation_id) if conversation_id else None,
                "message_id": str(message_id) if message_id else None,
                "max_iterations": max_iterations,
                "tools_selected_count": len(selected_names),
                "selected_tool_names": selected_names,
                "selection_reason_codes": list(cfg.selection_reason_codes),
                "conversation_mode": cfg.conversation_mode,
                "provider_streaming": not tools_enabled,
            },
        )
        logger.info(
            "agent_started user_id=%s conversation_id=%s message_id=%s "
            "max_iterations=%s tools_selected_count=%s selected_tool_names=%s "
            "reason_codes=%s conversation_mode=%s prompt_message_count=%s "
            "approximate_prompt_characters=%s memory_context_count=%s "
            "rag_context_count=%s request_id=%s",
            user.id,
            conversation_id,
            message_id,
            max_iterations,
            len(selected_names),
            selected_names,
            list(cfg.selection_reason_codes),
            cfg.conversation_mode,
            prompt_message_count,
            approx_prompt_chars,
            cfg.memory_context_count,
            cfg.rag_context_count,
            request_id,
        )

        working = list(messages)
        system_prompt = merge_system_prompt(system, tools_enabled=tools_enabled)
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
            # ── Non-tool turns: real progressive streaming ─────────────────
            if not tools_enabled:
                provider_streaming = True
                system_prompt = merge_system_prompt(system, tools_enabled=False)
                async for chunk, event, meta in self._stream_final_answer(
                    messages=working,
                    system_prompt=system_prompt,
                    temperature=cfg.temperature,
                    max_tokens=cfg.max_tokens,
                    cancel_check=cancel_check,
                ):
                    if event is None:
                        continue
                    if event.event in {StreamEventType.error, StreamEventType.agent_failed}:
                        yield event
                        return
                    if event.event == StreamEventType.delta and chunk:
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        final_content += chunk
                        generated_token_count += 1
                        yield event
                    if meta:
                        provider_name = str(meta.get("provider") or provider_name)
                        model_name = str(meta.get("model") or model_name)
                        raw_usage = meta.get("usage")
                        if isinstance(raw_usage, dict):
                            usage_acc["prompt_tokens"] = raw_usage.get("prompt_tokens")
                            usage_acc["completion_tokens"] = raw_usage.get("completion_tokens")
                            usage_acc["total_tokens"] = raw_usage.get("total_tokens")
                        finish_reason = str(meta.get("finish_reason") or "stop")
                yield StreamEvent(
                    event=StreamEventType.assistant_completed,
                    data={"content": final_content},
                )
            else:
                # ── Tool-calling path: generate for decisions, stream final ─
                # After tool results, another generate may request more tools
                # (multi-step). When the model returns plain text — or after the
                # last tool round — synthesize with stream() and no tool schemas.
                needs_synthesis_stream = False
                while iterations < max_iterations:
                    if await self._cancelled(cancel_check):
                        raise asyncio.CancelledError()
                    iterations += 1
                    generate_request = GenerateRequest(
                        messages=working,
                        system=system_prompt or None,
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
                    authorized_calls = []
                    for call in tool_calls:
                        if call.name not in selected_names or call.name not in KNOWN_TOOL_NAMES:
                            yield StreamEvent(
                                event=StreamEventType.tool_execution_failed,
                                data={
                                    "tool_call_id": call.id,
                                    "tool_name": call.name,
                                    "error_code": "tool_not_authorized",
                                    "error_message": (
                                        f"Tool '{call.name}' is not authorized for this turn"
                                    ),
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
                                        error=f"Tool '{call.name}' is not authorized",
                                    ),
                                )
                            )
                            continue
                        authorized_calls.append(call)

                    if not authorized_calls:
                        if tool_calls:
                            # Model requested tools outside the allow-list; continue so
                            # a later turn can recover with plain text or synthesis.
                            continue
                        final_content = generation.content or ""
                        finish_reason = generation.finish_reason or "stop"
                        if tool_execution_ids and not final_content.strip():
                            needs_synthesis_stream = True
                            break
                        if final_content:
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                            # After tools, final text often arrives via generate(); emit
                            # progressively. Empty finals use stream() above.
                            pieces = _progressive_chunks(final_content)
                            for piece in pieces:
                                generated_token_count += 1
                                yield StreamEvent(
                                    event=StreamEventType.delta,
                                    data={"content": piece},
                                )
                        yield StreamEvent(
                            event=StreamEventType.assistant_completed,
                            data={"content": final_content},
                        )
                        break

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
                                for call in authorized_calls
                            ],
                        )
                    )

                    for call in authorized_calls:
                        if await self._cancelled(cancel_check):
                            raise asyncio.CancelledError()
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
                                    "result": (
                                        result.data if result.expose_to_llm else {"ok": True}
                                    ),
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
                    # Continue loop so the model can request additional tools.
                else:
                    finish_reason = "max_tool_iterations"
                    needs_synthesis_stream = False
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

                if needs_synthesis_stream:
                    provider_streaming = True
                    synthesis_system = merge_system_prompt(system, tools_enabled=False)
                    async for chunk, event, meta in self._stream_final_answer(
                        messages=working,
                        system_prompt=synthesis_system,
                        temperature=cfg.temperature,
                        max_tokens=cfg.max_tokens,
                        cancel_check=cancel_check,
                    ):
                        if event is None:
                            continue
                        if event.event == StreamEventType.error:
                            yield event
                            return
                        if event.event == StreamEventType.delta and chunk:
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                            final_content += chunk
                            generated_token_count += 1
                            yield event
                        if meta:
                            provider_name = str(meta.get("provider") or provider_name)
                            model_name = str(meta.get("model") or model_name)
                            raw_usage = meta.get("usage")
                            if isinstance(raw_usage, dict):
                                usage_acc["prompt_tokens"] = raw_usage.get("prompt_tokens")
                                usage_acc["completion_tokens"] = raw_usage.get("completion_tokens")
                                usage_acc["total_tokens"] = raw_usage.get("total_tokens")
                            finish_reason = str(
                                meta.get("finish_reason") or finish_reason or "stop"
                            )
                    yield StreamEvent(
                        event=StreamEventType.assistant_completed,
                        data={"content": final_content},
                    )

            total_generation_ms = round((time.perf_counter() - started) * 1000, 2)
            ttft_ms = (
                round((first_token_at - started) * 1000, 2) if first_token_at is not None else None
            )
            yield StreamEvent(
                event=StreamEventType.agent_completed,
                data={
                    "iterations": iterations,
                    "tool_execution_ids": tool_execution_ids,
                    "finish_reason": finish_reason,
                    "provider": provider_name,
                    "model": model_name,
                    "usage": usage_acc,
                    "latency_ms": total_generation_ms,
                    "tools_selected_count": len(selected_names),
                    "selected_tool_names": selected_names,
                    "provider_streaming": provider_streaming,
                    "prompt_message_count": prompt_message_count,
                    "approximate_prompt_characters": approx_prompt_chars,
                    "time_to_first_token_ms": ttft_ms,
                    "total_generation_ms": total_generation_ms,
                    "generated_token_count": generated_token_count,
                    "cancellation_status": cancellation_status,
                    "conversation_mode": cfg.conversation_mode,
                    "memory_context_count": cfg.memory_context_count,
                    "rag_context_count": cfg.rag_context_count,
                },
            )
            logger.info(
                "agent_completed user_id=%s conversation_id=%s iterations=%s "
                "tools_selected_count=%s selected_tool_names=%s "
                "provider_streaming=%s time_to_first_token_ms=%s "
                "total_generation_ms=%s generated_token_count=%s "
                "cancellation_status=%s request_id=%s",
                user.id,
                conversation_id,
                iterations,
                len(selected_names),
                selected_names,
                provider_streaming,
                ttft_ms,
                total_generation_ms,
                generated_token_count,
                cancellation_status,
                request_id,
            )
        except asyncio.CancelledError:
            cancellation_status = "cancelled"
            total_generation_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "agent_cancelled user_id=%s conversation_id=%s message_id=%s "
                "partial_chars=%s total_generation_ms=%s request_id=%s",
                user.id,
                conversation_id,
                message_id,
                len(final_content),
                total_generation_ms,
                request_id,
            )
            yield StreamEvent(
                event=StreamEventType.agent_failed,
                data={
                    "error": {
                        "code": "client_disconnected",
                        "message": "Generation cancelled",
                    },
                    "cancellation_status": cancellation_status,
                    "partial_content_chars": len(final_content.strip()),
                },
            )
            raise
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
