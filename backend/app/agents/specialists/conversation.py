"""Conversation Agent — ordinary chat and final synthesis."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from app.agents.base import BaseAgent
from app.agents.capabilities import AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.prompts import AGENT_SYSTEM_POLICY, merge_system_prompt
from app.agents.schemas import AgentTaskRequest, AgentTaskResult
from app.agents.specialists.common import truncate_output
from app.core.config import Settings
from app.llm.schemas import ChatMessage, GenerateRequest, MessageRole

logger = logging.getLogger("cortexa.agents.conversation")


class ConversationSpecialist(BaseAgent):
    name: ClassVar[str] = "conversation"
    display_name: ClassVar[str] = "Conversation Agent"
    description: ClassVar[str] = (
        "Handles normal chat, synthesizes final responses, and remains "
        "the fallback for simple requests."
    )
    capabilities: ClassVar[frozenset[AgentCapability]] = frozenset(
        {
            AgentCapability.chat,
            AgentCapability.synthesize,
            AgentCapability.fallback,
        }
    )
    allowed_tools: ClassVar[frozenset[str]] = frozenset()
    maximum_steps: ClassVar[int] = 4
    timeout_seconds: ClassVar[int] = 120

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        llm_service: Any | None = None,
    ) -> None:
        self.settings = settings
        self.llm_service = llm_service

    async def execute(
        self,
        *,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        **kwargs: Any,
    ) -> AgentTaskResult:
        max_chars = (
            self.settings.agent_task_output_max_characters
            if self.settings is not None
            else context.limits.task_output_max_characters
        )
        prior = context.prior_task_results or []
        citations: list[dict[str, Any]] = []
        for item in prior:
            for cite in item.get("citations") or []:
                if isinstance(cite, dict):
                    citations.append(cite)

        if task.task_type in {"synthesize", "final_response"} or prior:
            content, llm_calls = await self._synthesize(context, task, max_chars=max_chars)
        else:
            content, llm_calls = await self._chat(context, task, max_chars=max_chars)

        # Never expose internal task/run IDs in the user-facing summary.
        safe = truncate_output(content, max_chars)
        for key in ("task_id", "run_id", "agent_run_id"):
            value = str(context.execution_metadata.get(key) or "")
            if value:
                safe = safe.replace(value, "[redacted]")

        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=truncate_output(safe, 2000),
            output={
                "content": safe,
                "citations": citations[:32],
                "prior_task_count": len(prior),
            },
            llm_calls_used=llm_calls,
        )


    def build_deterministic_fallback(
        self,
        *,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        max_chars: int | None = None,
    ) -> AgentTaskResult:
        """Build a safe final response without another provider call.

        This is used when local-model synthesis times out or becomes unavailable.
        It intentionally summarizes only already-approved specialist outputs and
        never invents a calculation, citation, or document fact.
        """
        limit = max_chars or (
            self.settings.agent_task_output_max_characters
            if self.settings is not None
            else context.limits.task_output_max_characters
        )
        prior = context.prior_task_results or []
        citations: list[dict[str, Any]] = []
        findings: list[str] = []
        missing_baseline = False

        for item in prior:
            agent = str(item.get("agent_name") or item.get("assigned_agent_key") or "specialist")
            summary = str(item.get("result_summary") or item.get("safe_summary") or "").strip()
            structured = item.get("structured_result") or item.get("output") or {}
            if summary:
                findings.append(f"{agent.title()}: {summary}")
            if isinstance(structured, dict):
                for cite in structured.get("citations") or item.get("citations") or []:
                    if isinstance(cite, dict):
                        citations.append(cite)
                tool_result = structured.get("tool_result")
                if isinstance(tool_result, dict) and tool_result.get("calculation_performed") is False:
                    missing_baseline = True

        lines = ["I completed the available parts of your request using the retrieved information."]
        if findings:
            lines.append("")
            lines.append("Findings:")
            lines.extend(f"- {finding}" for finding in findings[:8])
        if missing_baseline:
            lines.append("")
            lines.append(
                "The selected document does not provide a numeric baseline budget, so the 15% "
                "contingency cannot be calculated yet. Please provide the budget amount and I can "
                "calculate it immediately."
            )
        lines.append("")
        lines.append(
            "Recommendation: confirm the missing financial baseline, then review the identified "
            "operational and project risks before finalizing the contingency."
        )
        content = truncate_output("\n".join(lines), limit)
        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=truncate_output(content, 2000),
            output={
                "content": content,
                "citations": citations[:32],
                "prior_task_count": len(prior),
                "degraded_synthesis": True,
            },
            llm_calls_used=0,
        )

    async def _chat(
        self,
        context: AgentContextEnvelope,
        task: AgentTaskRequest,
        *,
        max_chars: int,
    ) -> tuple[str, int]:
        if self.llm_service is None:
            return truncate_output(f"Acknowledged: {task.objective}", max_chars), 0
        messages = self._build_messages(context, synthesis=False)
        response = await self.llm_service.generate(
            GenerateRequest(messages=messages, temperature=0.2, max_tokens=256)
        )
        return truncate_output(response.content or "", max_chars), 1

    async def _synthesize(
        self,
        context: AgentContextEnvelope,
        task: AgentTaskRequest,
        *,
        max_chars: int,
    ) -> tuple[str, int]:
        if self.llm_service is None:
            parts = [
                str(item.get("result_summary") or item.get("safe_summary") or "")
                for item in context.prior_task_results
            ]
            parts = [p for p in parts if p]
            if not parts:
                return (
                    "I could not find enough context to answer from prior specialist results.",
                    0,
                )
            return truncate_output(
                "Based on the gathered results:\n" + "\n".join(f"- {p}" for p in parts),
                max_chars,
            ), 0
        messages = self._build_messages(context, synthesis=True)
        response = await self.llm_service.generate(
            GenerateRequest(messages=messages, temperature=0.2, max_tokens=256)
        )
        return truncate_output(response.content or "", max_chars), 1

    def _build_messages(
        self,
        context: AgentContextEnvelope,
        *,
        synthesis: bool,
    ) -> list[ChatMessage]:
        system_bits = [AGENT_SYSTEM_POLICY.strip()]
        system_bits.append(
            "You are the Conversation Agent. The current user instruction has highest "
            "user-level priority. Use only approved memory and document context. "
            "Never invent citations. Never expose internal task IDs, run IDs, "
            "or hidden reasoning."
        )
        system = merge_system_prompt("\n\n".join(system_bits), tools_enabled=False)
        if synthesis:
            blocks: list[str] = ["Prior specialist results (safe summaries only):"]
            for item in context.prior_task_results:
                agent = item.get("agent_name") or item.get("assigned_agent_key") or "specialist"
                summary = item.get("result_summary") or item.get("safe_summary") or ""
                structured = item.get("structured_result") or item.get("output") or {}
                blocks.append(f"- {agent}: {summary}")
                if isinstance(structured, dict) and structured.get("facts"):
                    blocks.append(f"  facts: {structured.get('facts')}")
                if isinstance(structured, dict) and structured.get("tool_result"):
                    blocks.append(f"  tool_result: {structured.get('tool_result')}")
            if context.document_context:
                blocks.append("Document context is available via prior knowledge results.")
            if not context.prior_task_results and not context.document_context:
                blocks.append("No prior specialist context was available.")
            user_content = (
                f"User request: {context.user_request}\n\n"
                + "\n".join(blocks)
                + "\n\nWrite a direct, user-friendly final answer."
            )
        else:
            history_lines = [
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in context.selected_history[-8:]
            ]
            user_content = context.user_request
            if history_lines:
                user_content = (
                    "Recent conversation:\n"
                    + "\n".join(history_lines)
                    + f"\n\nCurrent user request: {context.user_request}"
                )
        return [
            ChatMessage(role=MessageRole.system, content=system),
            ChatMessage(role=MessageRole.user, content=user_content[:8000]),
        ]
