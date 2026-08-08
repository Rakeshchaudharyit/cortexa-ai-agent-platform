"""Deterministic planning policy for common multi-agent workflows.

The policy is intentionally provider-neutral and side-effect free. It converts
explicit capabilities and conservative lexical intent signals into a bounded
AgentPlan. Ambiguous requests return ``None`` so the Planning Specialist may
use its LLM fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.schemas import AgentComplexityDecision, AgentPlan, AgentPlanTask


@dataclass(frozen=True, slots=True)
class PlanningSignals:
    knowledge: bool
    tool: bool
    memory_read: bool
    memory_write: bool
    recommendation: bool
    forced: bool


class DeterministicPlanningEngine:
    """Create fast, auditable plans for known orchestration patterns."""

    _KNOWLEDGE_TERMS = (
        "knowledge",
        "document",
        "documents",
        "file",
        "files",
        "report",
        "contract",
        "architecture",
        "technical themes",
        "available knowledge",
        "review",
        "analyze",
        "analyse",
        "summarize",
        "summarise",
        "compare",
    )
    _TOOL_TERMS = (
        "calculate",
        "calculation",
        "compute",
        "percentage",
        "percent",
        "total",
        "date",
        "time",
        "timezone",
    )
    _MEMORY_READ_TERMS = (
        "saved preference",
        "saved preferences",
        "my preferences",
        "remembered",
        "memory",
        "previous decision",
    )
    _MEMORY_WRITE_TERMS = (
        "remember this",
        "save this preference",
        "store this preference",
        "remember my",
    )
    _RECOMMENDATION_TERMS = (
        "recommend",
        "recommendation",
        "prioritize",
        "prioritise",
        "implementation plan",
        "strategy",
        "risks",
        "options",
        "proposal",
        "draft",
    )

    def build_plan(
        self,
        *,
        user_request: str,
        decision: AgentComplexityDecision,
        enabled_tool_names: frozenset[str],
        selected_document_ids: list[str],
        memory_enabled: bool,
        execution_profile: str = "fast",
    ) -> AgentPlan | None:
        """Return a deterministic plan or ``None`` for an ambiguous request."""
        signals = self._signals(
            user_request=user_request,
            decision=decision,
            selected_document_ids=selected_document_ids,
            memory_enabled=memory_enabled,
        )

        # A forced browser run with explicit review/recommendation language is
        # a known Knowledge -> Conversation workflow even when no documents
        # were explicitly selected (the chat pipeline can search all allowed
        # documents).
        if not any(
            (
                signals.knowledge,
                signals.tool,
                signals.memory_read,
                signals.memory_write,
                signals.recommendation,
            )
        ):
            return None

        goal = _truncate(user_request, 500)
        tasks: list[AgentPlanTask] = []
        sequence = 1
        dependency_sequences: list[int] = []

        if signals.memory_read:
            tasks.append(
                AgentPlanTask(
                    sequence=sequence,
                    agent_name="memory",
                    task_type="retrieve_memories",
                    objective="Retrieve approved memories relevant to the request",
                    expected_output="Bounded memory summaries",
                    maximum_retries=0 if execution_profile == "fast" else 1,
                )
            )
            dependency_sequences.append(sequence)
            sequence += 1

        if signals.knowledge:
            tasks.append(
                AgentPlanTask(
                    sequence=sequence,
                    agent_name="knowledge",
                    task_type="retrieve",
                    objective="Retrieve and summarize relevant facts from available knowledge",
                    expected_output="Bounded facts and citations",
                    maximum_retries=0 if execution_profile == "fast" else 1,
                )
            )
            knowledge_sequence = sequence
            dependency_sequences.append(sequence)
            sequence += 1
        else:
            knowledge_sequence = None

        if signals.tool:
            allowed_tools = self._select_tools(user_request, enabled_tool_names)
            if allowed_tools:
                tool_dependencies = [knowledge_sequence] if knowledge_sequence is not None else []
                tasks.append(
                    AgentPlanTask(
                        sequence=sequence,
                        agent_name="tool",
                        task_type="compute",
                        objective="Perform the required deterministic calculation or lookup",
                        dependencies=tool_dependencies,
                        allowed_tools=allowed_tools,
                        expected_output="Structured tool result",
                        maximum_retries=0 if execution_profile == "fast" else 1,
                    )
                )
                dependency_sequences.append(sequence)
                sequence += 1

        # Keep common interactive plans at four tasks or fewer. Explicit memory
        # writes are approval-gated and only included when there is room.
        requires_approval = False
        if signals.memory_write and sequence <= 3:
            tasks.append(
                AgentPlanTask(
                    sequence=sequence,
                    agent_name="memory",
                    task_type="propose_write",
                    objective="Propose an approval-gated memory update",
                    dependencies=list(dependency_sequences),
                    requires_approval=True,
                    expected_output="Approval-required memory proposal",
                    maximum_retries=0,
                )
            )
            dependency_sequences.append(sequence)
            sequence += 1
            requires_approval = True

        # Every deterministic plan ends in a user-facing response. This also
        # guarantees the plan is never empty.
        tasks.append(
            AgentPlanTask(
                sequence=sequence,
                agent_name="conversation",
                task_type="synthesize" if dependency_sequences else "respond",
                objective=(
                    "Synthesize a concise prioritized recommendation from specialist results"
                    if dependency_sequences
                    else "Provide the requested user-facing response"
                ),
                dependencies=list(dependency_sequences),
                expected_output="User-facing answer",
                maximum_retries=0 if execution_profile == "fast" else 1,
            )
        )

        # Defensive cap for the interactive architecture. The rule construction
        # above normally yields <=4 tasks; fail closed to the LLM path rather
        # than silently truncating dependencies.
        if len(tasks) > 4:
            return None

        specialists = [task.agent_name for task in tasks if task.agent_name != "conversation"]
        summary = (
            "Using a deterministic plan for "
            + (", ".join(specialists) if specialists else "direct response")
            + " followed by final synthesis."
        )
        return AgentPlan(
            goal=goal,
            requires_multi_agent=bool(specialists),
            reasoning_summary=summary,
            tasks=tasks,
            final_response_agent="conversation",
            estimated_steps=len(tasks),
            requires_approval=requires_approval,
            planning_strategy="deterministic",
        )

    def _signals(
        self,
        *,
        user_request: str,
        decision: AgentComplexityDecision,
        selected_document_ids: list[str],
        memory_enabled: bool,
    ) -> PlanningSignals:
        text = " ".join(user_request.lower().split())
        codes = set(decision.reason_codes)
        suggested = set(decision.suggested_agents)
        forced = "user_forced_multi_agent" in codes

        knowledge = (
            "knowledge" in suggested
            or bool(selected_document_ids)
            or any(term in text for term in self._KNOWLEDGE_TERMS)
            or any("knowledge" in code or "document" in code for code in codes)
        )
        tool = (
            "tool" in suggested
            or any(term in text for term in self._TOOL_TERMS)
            or any("tool" in code or "calc" in code or "datetime" in code for code in codes)
        )
        memory_read = memory_enabled and (
            "memory" in suggested
            or any(term in text for term in self._MEMORY_READ_TERMS)
            or any("memory" in code for code in codes)
        )
        memory_write = memory_enabled and any(
            term in text for term in self._MEMORY_WRITE_TERMS
        )
        recommendation = any(term in text for term in self._RECOMMENDATION_TERMS)

        # The explicit Agent Runs launcher suggests knowledge + conversation.
        # Only honor that hint when the request itself contains a review or
        # recommendation signal, avoiding unnecessary retrieval for unrelated
        # forced requests.
        if forced and recommendation and "knowledge" in suggested:
            knowledge = True

        return PlanningSignals(
            knowledge=knowledge,
            tool=tool,
            memory_read=memory_read,
            memory_write=memory_write,
            recommendation=recommendation,
            forced=forced,
        )

    @staticmethod
    def _select_tools(
        user_request: str,
        enabled_tool_names: frozenset[str],
    ) -> list[str]:
        text = user_request.lower()
        selected: list[str] = []
        if "calculator" in enabled_tool_names and any(
            term in text
            for term in ("calculate", "calculation", "compute", "percent", "total")
        ):
            selected.append("calculator")
        if "current_datetime" in enabled_tool_names and any(
            term in text for term in ("date", "time", "timezone")
        ):
            selected.append("current_datetime")
        return selected[:2]


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1].rstrip() + "…"
