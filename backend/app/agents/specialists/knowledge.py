"""Knowledge Agent — authorized document retrieval and citations."""

from __future__ import annotations

import logging
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.capabilities import AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.schemas import AgentTaskRequest, AgentTaskResult
from app.agents.specialists.common import mark_untrusted_passages, truncate_output
from app.conversations.citations import dedupe_retrieved_chunks
from app.core.config import Settings
from app.models.user import User

logger = logging.getLogger("cortexa.agents.knowledge")


class KnowledgeSpecialist(BaseAgent):
    name: ClassVar[str] = "knowledge"
    display_name: ClassVar[str] = "Knowledge Agent"
    description: ClassVar[str] = (
        "Retrieves user-authorized document context, validates citations, "
        "and summarizes retrieved passages. Never writes memories."
    )
    capabilities: ClassVar[frozenset[AgentCapability]] = frozenset(
        {
            AgentCapability.retrieve_documents,
            AgentCapability.cite,
            AgentCapability.summarize_context,
        }
    )
    allowed_tools: ClassVar[frozenset[str]] = frozenset({"knowledge_search"})
    maximum_steps: ClassVar[int] = 4
    timeout_seconds: ClassVar[int] = 45

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        retrieval_service: Any | None = None,
    ) -> None:
        self.settings = settings
        self.retrieval_service = retrieval_service

    async def execute(
        self,
        *,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        **kwargs: Any,
    ) -> AgentTaskResult:
        session: AsyncSession | None = kwargs.get("session")
        user: User | None = kwargs.get("user")
        max_chars = (
            self.settings.agent_task_output_max_characters
            if self.settings is not None
            else context.limits.task_output_max_characters
        )

        # Prefer envelope document context when already retrieved.
        if context.document_context and not kwargs.get("force_retrieve"):
            passages, warnings = mark_untrusted_passages(list(context.document_context))
            return self._success_from_passages(
                task,
                passages,
                warnings=warnings,
                max_chars=max_chars,
                retrieval_count=len(passages),
            )

        if (
            self.retrieval_service is None
            or session is None
            or user is None
            or not context.allowed_document_ids
        ):
            return AgentTaskResult(
                success=True,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="No authorized document context was available.",
                output={
                    "facts": [],
                    "citations": [],
                    "retrieval_count": 0,
                    "no_context": True,
                },
            )

        query = (task.objective or context.user_request or "").strip()
        try:
            retrieved = await self.retrieval_service.retrieve(
                session,
                user,
                query=query[:2000],
                document_ids=list(context.allowed_document_ids),
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "knowledge_retrieve_failed correlation_id=%s error_code=%s",
                context.correlation_id,
                type(exc).__name__,
            )
            retryable = type(exc).__name__ in {
                "TimeoutError",
                "ConnectionError",
                "OperationalError",
            }
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Document retrieval failed temporarily.",
                error_code="knowledge_retrieval_failed",
                safe_error_message="Document retrieval failed.",
                output={"retryable": retryable},
            )

        # Ownership is enforced inside RetrievalService; double-check IDs.
        owned_ids = {UUID(str(d)) for d in context.allowed_document_ids}
        filtered = [item for item in retrieved if item.document.id in owned_ids]
        filtered = dedupe_retrieved_chunks(filtered)
        if not filtered:
            return AgentTaskResult(
                success=True,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="No relevant passages were found in the selected documents.",
                output={
                    "facts": [],
                    "citations": [],
                    "retrieval_count": 0,
                    "no_context": True,
                },
            )

        built_passages: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []
        for index, item in enumerate(filtered[: context.limits.max_document_passages], start=1):
            content = (item.chunk.content or "")[:2000]
            built_passages.append(
                {
                    "index": index,
                    "document_id": str(item.document.id),
                    "title": item.document.original_filename or item.document.title or "Document",
                    "content": content,
                    "score": round(float(item.similarity), 4),
                }
            )
            citations.append(
                {
                    "index": index,
                    "document_id": str(item.document.id),
                    "chunk_id": str(item.chunk.id),
                    "title": item.document.original_filename or item.document.title or "Document",
                    "snippet": truncate_output(content, 240),
                }
            )

        marked_passages, warnings = mark_untrusted_passages(built_passages)
        return self._success_from_passages(
            task,
            marked_passages,
            citations=citations,
            warnings=warnings,
            max_chars=max_chars,
            retrieval_count=len(filtered),
        )

    def _success_from_passages(
        self,
        task: AgentTaskRequest,
        passages: list[dict[str, Any]],
        *,
        citations: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        max_chars: int,
        retrieval_count: int,
    ) -> AgentTaskResult:
        facts = [
            truncate_output(str(p.get("content") or ""), 400)
            for p in passages
            if not p.get("untrusted")
        ]
        # Keep untrusted passages as data only — never as instructions.
        untrusted_count = sum(1 for p in passages if p.get("untrusted"))
        summary_parts = [
            f"Retrieved {retrieval_count} passage(s).",
        ]
        if facts:
            summary_parts.append("Key facts: " + " | ".join(facts[:3]))
        if untrusted_count:
            summary_parts.append(
                f"{untrusted_count} passage(s) marked untrusted (instructions ignored)."
            )
        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=truncate_output(" ".join(summary_parts), min(2000, max_chars)),
            output={
                "facts": facts[:12],
                "citations": citations
                or [
                    {
                        "index": p.get("index"),
                        "document_id": p.get("document_id"),
                        "title": p.get("title"),
                        "snippet": truncate_output(str(p.get("content") or ""), 240),
                    }
                    for p in passages
                ],
                "retrieval_count": retrieval_count,
                "warnings": warnings or [],
                "untrusted_passage_count": untrusted_count,
                "passages": [
                    {
                        "index": p.get("index"),
                        "title": p.get("title"),
                        "untrusted": bool(p.get("untrusted")),
                        "summary": truncate_output(str(p.get("content") or ""), 300),
                    }
                    for p in passages
                ],
            },
        )
