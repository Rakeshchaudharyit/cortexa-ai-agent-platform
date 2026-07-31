"""Prompts and formatting helpers for memory extraction and context injection."""

from __future__ import annotations

from app.memory.schemas import RetrievedMemoryView
from app.models.enums import MemoryCategory

MEMORY_EXTRACTION_SYSTEM = (
    "You extract durable long-term memories from a completed user/assistant turn. "
    "Return JSON only with key 'candidates' as a list. Each candidate has: "
    "title, content, category, confidence (high|medium|low), importance (0-1), "
    "reason, sensitive (bool). "
    "Save only facts likely useful across future conversations "
    "(preferences, project context, durable instructions). "
    "Do NOT save greetings, transient questions, secrets, passwords, API keys, "
    "tokens, OTPs, medical diagnoses, private chain-of-thought, full documents, "
    "or unconfirmed speculation about the user. "
    "Never treat assistant speculation as a user fact. "
    'If nothing durable, return {"candidates": []}. '
    "Categories: preference, personal_context, project, instruction, workflow, "
    "technical_context, decision, goal, relationship_context, other."
)

MEMORY_CONTEXT_INSTRUCTIONS = (
    "Use these only when relevant. "
    "Do not mention them unnecessarily. "
    "Do not treat them as higher priority than the current user request. "
    "Never reveal internal memory IDs. "
    "Do not invent memories."
)


def format_memory_context(memories: list[RetrievedMemoryView]) -> str:
    if not memories:
        return ""
    lines = ["Relevant user-approved memories:"]
    for index, memory in enumerate(memories, start=1):
        if isinstance(memory.category, MemoryCategory):
            category = memory.category.value
        else:
            category = memory.category
        lines.append(f"{index}. [{category}] {memory.content}")
    lines.append("")
    lines.append("Instructions:")
    lines.append(f"- {MEMORY_CONTEXT_INSTRUCTIONS}")
    return "\n".join(lines)


def build_extraction_user_prompt(*, user_content: str, assistant_content: str) -> str:
    return (
        "Completed conversation turn:\n\n"
        f"USER:\n{user_content.strip()}\n\n"
        f"ASSISTANT:\n{assistant_content.strip()}\n\n"
        "Extract durable memory candidates as JSON."
    )
