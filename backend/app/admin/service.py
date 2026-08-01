"""Enterprise administration application service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.analytics import daterange_days, empty_analytics_points, merge_series
from app.admin.audit import record_admin_action
from app.admin.exceptions import (
    AdminNotFoundError,
    AdminValidationError,
    LastAdminProtectionError,
)
from app.admin.policies import (
    SAFE_SETTING_KEYS,
    UNSAFE_SETTING_KEYS,
    clamp_page_size,
    is_safe_setting_key,
)
from app.admin.repository import AdminRepository
from app.admin.schemas import (
    AdminAiActivitySummary,
    AdminAnalyticsPoint,
    AdminAnalyticsResponse,
    AdminAuditEventSummary,
    AdminAuditListResponse,
    AdminConversationDetail,
    AdminConversationListResponse,
    AdminConversationSummary,
    AdminDashboardResponse,
    AdminDocumentDetail,
    AdminDocumentListResponse,
    AdminDocumentSummary,
    AdminMemoryDetail,
    AdminMemoryListResponse,
    AdminMemorySummary,
    AdminMetricCard,
    AdminRecentActivityItem,
    AdminRevokeSessionsResponse,
    AdminSettingItem,
    AdminSettingsResponse,
    AdminSettingsUpdateResponse,
    AdminStatusCount,
    AdminSystemComponentStatus,
    AdminSystemHealthResponse,
    AdminSystemStatusSummary,
    AdminToolExecutionDetail,
    AdminToolExecutionListResponse,
    AdminToolExecutionSummary,
    AdminToolListResponse,
    AdminToolSummary,
    AdminToolUpdateResponse,
    AdminToolUsageStat,
    AdminTrendPoint,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserSummary,
    AdminUserUpdateResponse,
)
from app.admin.settings import (
    merge_effective_settings,
    runtime_settings_snapshot,
    validate_setting_value,
)
from app.core.config import Settings
from app.models.document import EMBEDDING_DIMENSION
from app.models.enums import (
    DocumentStatus,
    MemoryStatus,
    UserRole,
    UserStatus,
)
from app.models.memory import UserMemory
from app.models.user import User
from app.services.auth import AuthService
from app.services.tools import _summary_from_mapping
from app.tools.registry import ToolRegistry, ToolRuntimeOverride

logger = logging.getLogger("cortexa.admin")


class AdminService:
    """Orchestrates admin listings, mutations, analytics, and auditing."""

    def __init__(
        self,
        *,
        settings: Settings,
        auth_service: AuthService,
        tool_registry: ToolRegistry | None = None,
        document_service: Any | None = None,
        memory_service: Any | None = None,
        health_service: Any | None = None,
        repository: AdminRepository | None = None,
    ) -> None:
        self.settings = settings
        self.auth_service = auth_service
        self.tool_registry = tool_registry
        self.document_service = document_service
        self.memory_service = memory_service
        self.health_service = health_service
        self.repo = repository or AdminRepository()

    async def refresh_tool_overrides(self, session: AsyncSession) -> None:
        if self.tool_registry is None:
            return
        rows = await self.repo.list_tool_configurations(session)
        overrides: dict[str, ToolRuntimeOverride] = {}
        for row in rows:
            overrides[row.tool_name] = ToolRuntimeOverride(
                enabled=row.enabled,
                timeout_seconds=row.timeout_override,
                confirmation_required=row.confirmation_required_override,
            )
        self.tool_registry.apply_overrides(overrides)

    # ── Dashboard ──────────────────────────────────────────────────────────

    async def get_dashboard(
        self,
        session: AsyncSession,
        *,
        system_status: AdminSystemStatusSummary | None = None,
    ) -> AdminDashboardResponse:
        counts = await self.repo.dashboard_counts(session)
        trend_raw = await self.repo.usage_trend(session, days=14)
        tool_stats = await self.repo.tool_execution_stats(session)
        activity = await self.repo.recent_platform_activity(session, limit=12)

        metrics = [
            AdminMetricCard(key="users_total", label="Total users", value=counts["users_total"]),
            AdminMetricCard(key="users_active", label="Active users", value=counts["users_active"]),
            AdminMetricCard(
                key="users_disabled", label="Disabled users", value=counts["users_disabled"]
            ),
            AdminMetricCard(
                key="documents_total", label="Total documents", value=counts["documents_total"]
            ),
            AdminMetricCard(
                key="documents_ready", label="Ready documents", value=counts["documents_ready"]
            ),
            AdminMetricCard(
                key="documents_failed", label="Failed documents", value=counts["documents_failed"]
            ),
            AdminMetricCard(
                key="conversations_total",
                label="Conversations",
                value=counts["conversations_total"],
            ),
            AdminMetricCard(
                key="messages_24h", label="Messages (24h)", value=counts["messages_24h"]
            ),
            AdminMetricCard(
                key="memories_active", label="Active memories", value=counts["memories_active"]
            ),
            AdminMetricCard(
                key="tool_executions", label="Tool executions", value=counts["tool_executions"]
            ),
            AdminMetricCard(
                key="tool_success_rate",
                label="Tool success rate",
                value=(
                    round(counts["tool_success_rate"] * 100, 1)
                    if counts["tool_success_rate"] is not None
                    else None
                ),
                unit="%",
                unavailable=counts["tool_success_rate"] is None,
            ),
            AdminMetricCard(
                key="average_response_time_ms",
                label="Avg response time",
                value=(
                    round(counts["average_response_time_ms"], 1)
                    if counts["average_response_time_ms"] is not None
                    else None
                ),
                unit="ms",
                unavailable=counts["average_response_time_ms"] is None,
            ),
            AdminMetricCard(
                key="failed_ai_requests",
                label="Failed AI requests",
                value=counts["failed_ai_requests"],
            ),
        ]

        tool_usage = [
            AdminToolUsageStat(
                tool_name=name,
                executions=int(stat["execution_count"]),
                succeeded=int(stat["succeeded"]),
                failed=int(stat["execution_count"]) - int(stat["succeeded"]),
                success_rate=stat["success_rate"],
            )
            for name, stat in sorted(tool_stats.items())
        ]

        return AdminDashboardResponse(
            metrics=metrics,
            usage_trend=[AdminTrendPoint(**point) for point in trend_raw],
            ai_activity=AdminAiActivitySummary(
                provider=self.settings.llm_provider,
                model=self.settings.ollama_model,
                average_latency_ms=counts["average_response_time_ms"],
                successful_requests=None,
                failed_requests=counts["failed_ai_requests"],
                available=None,
                note="Token/cost analytics unavailable in Phase 8",
            ),
            document_pipeline=[
                AdminStatusCount(status="ready", count=counts["documents_ready"]),
                AdminStatusCount(status="processing", count=counts["documents_processing"]),
                AdminStatusCount(status="failed", count=counts["documents_failed"]),
            ],
            tool_usage=tool_usage,
            recent_activity=[AdminRecentActivityItem(**item) for item in activity],
            system_status=system_status
            or AdminSystemStatusSummary(
                backend="unknown",
                postgres="unknown",
                redis="unknown",
                ollama="unknown",
                embedding_model=self.settings.ollama_embedding_model,
                migrations="unknown",
                storage="unknown",
                database_identity=self.settings.expected_database_identity,
                app_version=self.settings.app_version,
                environment=self.settings.app_env,
            ),
            generated_at=datetime.now(UTC),
        )

    # ── Users ──────────────────────────────────────────────────────────────

    def _user_summary(self, row: dict[str, Any]) -> AdminUserSummary:
        user: User = row["user"]
        return AdminUserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            status=user.status,
            is_email_verified=user.is_email_verified,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            conversations_count=row["conversations_count"],
            documents_count=row["documents_count"],
            memories_count=row["memories_count"],
        )

    async def list_users(
        self,
        session: AsyncSession,
        *,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
        role: UserRole | None = None,
        status: UserStatus | None = None,
        verified: bool | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> AdminUserListResponse:
        limit = clamp_page_size(limit)
        offset = max(0, offset)
        rows, total = await self.repo.list_users(
            session,
            limit=limit,
            offset=offset,
            search=search,
            role=role,
            status=status,
            verified=verified,
            created_from=created_from,
            created_to=created_to,
        )
        return AdminUserListResponse(
            items=[self._user_summary(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_user(self, session: AsyncSession, user_id: uuid.UUID) -> AdminUserDetail:
        user = await self.repo.get_user(session, user_id)
        counts = await self.repo.user_resource_counts(session, user_id)
        return AdminUserDetail(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            status=user.status,
            is_email_verified=user.is_email_verified,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            conversations_count=counts["conversations_count"],
            documents_count=counts["documents_count"],
            memories_count=counts["memories_count"],
            active_sessions_count=counts["active_sessions_count"],
            tool_executions_count=counts["tool_executions_count"],
            tool_success_count=counts["tool_success_count"],
            tool_failure_count=counts["tool_failure_count"],
            recent_activity=[],
        )

    async def update_user(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
        role: UserRole | None = None,
        status: UserStatus | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUserUpdateResponse:
        if role is None and status is None:
            raise AdminValidationError("Provide role and/or status to update")
        user = await self.repo.get_user(session, user_id)
        sessions_revoked = 0
        previous_role = user.role
        previous_status = user.status

        if role is not None and role != user.role:
            if user.role == UserRole.admin and role != UserRole.admin:
                active_admins = await self.repo.count_active_admins(session)
                if active_admins <= 1 and user.status == UserStatus.active:
                    raise LastAdminProtectionError()
            user.role = role
            await record_admin_action(
                session,
                actor_user_id=actor.id,
                action="role_changed",
                target_type="user",
                target_id=str(user.id),
                target_user_id=user.id,
                safe_summary=f"Role changed from {previous_role.value} to {role.value}",
                metadata={"from": previous_role.value, "to": role.value},
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        if status is not None and status != user.status:
            if (
                user.role == UserRole.admin
                and user.status == UserStatus.active
                and status == UserStatus.disabled
            ):
                active_admins = await self.repo.count_active_admins(session)
                if active_admins <= 1:
                    raise LastAdminProtectionError()
            user.status = status
            await record_admin_action(
                session,
                actor_user_id=actor.id,
                action="account_status_changed",
                target_type="user",
                target_id=str(user.id),
                target_user_id=user.id,
                safe_summary=(
                    f"Account status changed from {previous_status.value} to {status.value}"
                ),
                metadata={"from": previous_status.value, "to": status.value},
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            if status == UserStatus.disabled:
                sessions_revoked = await self.auth_service.revoke_all_user_sessions(
                    session, user_id=user.id, commit=False
                )
                await record_admin_action(
                    session,
                    actor_user_id=actor.id,
                    action="sessions_revoked",
                    target_type="user",
                    target_id=str(user.id),
                    target_user_id=user.id,
                    safe_summary=f"Revoked {sessions_revoked} refresh session(s) after disable",
                    metadata={"sessions_revoked": sessions_revoked},
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

        user.updated_at = datetime.now(UTC)
        await session.commit()
        detail = await self.get_user(session, user.id)
        return AdminUserUpdateResponse(user=detail, sessions_revoked=sessions_revoked)

    async def revoke_user_sessions(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminRevokeSessionsResponse:
        user = await self.repo.get_user(session, user_id)
        revoked = await self.auth_service.revoke_all_user_sessions(
            session, user_id=user.id, commit=False
        )
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="sessions_revoked",
            target_type="user",
            target_id=str(user.id),
            target_user_id=user.id,
            safe_summary=f"Revoked {revoked} active refresh session(s)",
            metadata={"sessions_revoked": revoked},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        return AdminRevokeSessionsResponse(user_id=user.id, sessions_revoked=revoked)


    async def record_admin_login_success(
        self,
        session: AsyncSession,
        *,
        actor: User,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="admin_login_success",
            target_type="session",
            target_id=str(actor.id),
            target_user_id=actor.id,
            safe_summary="Administrator signed in to the admin portal",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            commit=True,
        )

    async def record_admin_login_denied(
        self,
        session: AsyncSession,
        *,
        actor: User,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="admin_login_denied",
            target_type="session",
            target_id=str(actor.id),
            target_user_id=actor.id,
            safe_summary="Authenticated non-admin attempted admin portal login",
            metadata={"role": actor.role.value},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            commit=True,
        )

    # ── Documents ──────────────────────────────────────────────────────────

    def _document_summary(self, document: Any, owner: User) -> AdminDocumentSummary:
        duration = None
        if document.processed_at and document.created_at:
            duration = (document.processed_at - document.created_at).total_seconds() * 1000
        return AdminDocumentSummary(
            id=document.id,
            filename=document.original_filename,
            owner_id=owner.id,
            owner_email=owner.email,
            owner_name=owner.full_name,
            media_type=document.media_type,
            status=document.status,
            size_bytes=document.file_size_bytes,
            chunk_count=document.chunk_count,
            created_at=document.created_at,
            processed_at=document.processed_at,
            processing_duration_ms=duration,
            error_code=document.error_code,
        )

    async def list_documents(
        self, session: AsyncSession, **kwargs: Any
    ) -> AdminDocumentListResponse:
        limit = clamp_page_size(kwargs.pop("limit", 20))
        offset = max(0, int(kwargs.pop("offset", 0)))
        rows, total = await self.repo.list_documents(session, limit=limit, offset=offset, **kwargs)
        return AdminDocumentListResponse(
            items=[self._document_summary(doc, owner) for doc, owner in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_document(
        self, session: AsyncSession, document_id: uuid.UUID, *, include_excerpts: bool = False
    ) -> AdminDocumentDetail:
        document, owner = await self.repo.get_document(session, document_id)
        excerpts: list[str] = []
        if include_excerpts and document.status == DocumentStatus.ready:
            excerpts = await self.repo.sample_chunk_excerpts(session, document.id)
        base = self._document_summary(document, owner)
        return AdminDocumentDetail(
            **base.model_dump(),
            checksum=document.checksum_sha256,
            storage_key=None,  # never expose filesystem paths
            character_count=document.character_count,
            embedding_dimension=EMBEDDING_DIMENSION if document.chunk_count else None,
            error_message=document.error_message,
            excerpt_samples=excerpts,
            updated_at=document.updated_at,
        )

    async def reprocess_document(
        self,
        session: AsyncSession,
        *,
        actor: User,
        document_id: uuid.UUID,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminDocumentDetail:
        if self.document_service is None or not hasattr(
            self.document_service, "reprocess_document"
        ):
            raise AdminValidationError("Document reprocess is not available in this environment")
        document, _owner = await self.repo.get_document(session, document_id)
        await self.document_service.reprocess_document(session, document)
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="document_reprocessed",
            target_type="document",
            target_id=str(document_id),
            target_user_id=document.user_id,
            safe_summary="Document reprocessed by administrator",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        return await self.get_document(session, document_id)

    async def delete_document(
        self,
        session: AsyncSession,
        *,
        actor: User,
        document_id: uuid.UUID,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        document, owner = await self.repo.get_document(session, document_id)
        if self.document_service is None:
            raise AdminValidationError("Document service unavailable")
        # Reuse ownership-scoped delete by acting as owner for storage cleanup.
        await self.document_service.delete_document(session, owner, document_id)
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="document_deleted",
            target_type="document",
            target_id=str(document_id),
            target_user_id=owner.id,
            safe_summary="Document deleted by administrator",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            commit=True,
        )

    # ── Conversations ──────────────────────────────────────────────────────

    def _conversation_summary(self, row: dict[str, Any]) -> AdminConversationSummary:
        conv = row["conversation"]
        owner: User = row["owner"]
        grounded = bool(conv.default_document_scope) if conv.default_document_scope else False
        meta = conv.conversation_metadata if isinstance(conv.conversation_metadata, dict) else {}
        if "mode" in meta:
            grounded = str(meta.get("mode")).lower() in {"grounded", "rag", "documents"}
        return AdminConversationSummary(
            id=conv.id,
            title=conv.title,
            owner_id=owner.id,
            owner_email=owner.email,
            owner_name=owner.full_name,
            status=conv.status,
            message_count=row["message_count"],
            last_activity_at=conv.last_message_at or conv.updated_at,
            grounded_mode=grounded,
            memory_enabled=conv.memory_enabled_override,
            tool_execution_count=row["tool_execution_count"],
            created_at=conv.created_at,
        )

    async def list_conversations(
        self, session: AsyncSession, **kwargs: Any
    ) -> AdminConversationListResponse:
        limit = clamp_page_size(kwargs.pop("limit", 20))
        offset = max(0, int(kwargs.pop("offset", 0)))
        rows, total = await self.repo.list_conversations(
            session, limit=limit, offset=offset, **kwargs
        )
        return AdminConversationListResponse(
            items=[self._conversation_summary(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_conversation(
        self, session: AsyncSession, conversation_id: uuid.UUID
    ) -> AdminConversationDetail:
        data = await self.repo.get_conversation(session, conversation_id)
        summary = self._conversation_summary(
            {
                "conversation": data["conversation"],
                "owner": data["owner"],
                "message_count": data["message_count"],
                "tool_execution_count": data["tool_execution_count"],
            }
        )
        timeline = [
            {
                "id": str(t.id),
                "tool_name": t.tool_name,
                "status": t.status.value,
                "started_at": t.started_at.isoformat(),
                "duration_ms": t.duration_ms,
                "error_code": t.error_code,
            }
            for t in data["tools"]
        ]
        return AdminConversationDetail(
            **summary.model_dump(),
            citations_count=data["citations_count"],
            memory_use_count=0,
            average_latency_ms=data["average_latency_ms"],
            failed_message_count=data["failed_message_count"],
            tool_timeline=timeline,
        )

    # ── Memories ───────────────────────────────────────────────────────────

    def _memory_summary(self, memory: UserMemory, owner: User) -> AdminMemorySummary:
        return AdminMemorySummary(
            id=memory.id,
            title=memory.title if memory.status != MemoryStatus.deleted else "[deleted]",
            owner_id=owner.id,
            owner_email=owner.email,
            owner_name=owner.full_name,
            category=memory.category,
            status=memory.status,
            source=memory.source,
            created_at=memory.created_at,
            last_used_at=memory.last_used_at,
            use_count=memory.use_count,
        )

    async def list_memories(self, session: AsyncSession, **kwargs: Any) -> AdminMemoryListResponse:
        limit = clamp_page_size(kwargs.pop("limit", 20))
        offset = max(0, int(kwargs.pop("offset", 0)))
        rows, total = await self.repo.list_memories(session, limit=limit, offset=offset, **kwargs)
        return AdminMemoryListResponse(
            items=[self._memory_summary(m, u) for m, u in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_memory(self, session: AsyncSession, memory_id: uuid.UUID) -> AdminMemoryDetail:
        memory, owner = await self.repo.get_memory(session, memory_id)
        events = await self.repo.memory_audit_events(session, memory_id)
        preview = None
        redacted = memory.status in {MemoryStatus.deleted, MemoryStatus.rejected}
        if not redacted and memory.content:
            preview = memory.content[:200] + ("…" if len(memory.content) > 200 else "")
        base = self._memory_summary(memory, owner)
        return AdminMemoryDetail(
            **base.model_dump(),
            confidence=memory.confidence.value if memory.confidence else None,
            importance=int(memory.importance * 100) if memory.importance is not None else None,
            content_preview=preview,
            content_redacted=redacted,
            audit_events=[
                {
                    "event_type": e.event_type.value
                    if hasattr(e.event_type, "value")
                    else str(e.event_type),
                    "created_at": e.created_at.isoformat(),
                    "safe_metadata": e.safe_metadata_json,
                }
                for e in events
            ],
        )

    async def _memory_owner_action(
        self,
        session: AsyncSession,
        *,
        actor: User,
        memory_id: uuid.UUID,
        action: str,
        request_id: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AdminMemoryDetail:
        if self.memory_service is None:
            raise AdminValidationError("Memory service unavailable")
        memory, owner = await self.repo.get_memory(session, memory_id)
        if action == "archive":
            await self.memory_service.archive(session, owner, memory_id)
            audit_action = "memory_archived"
        elif action == "reject":
            await self.memory_service.reject(session, owner, memory_id)
            audit_action = "memory_rejected"
        elif action == "delete":
            await self.memory_service.delete_memory(session, owner, memory_id)
            audit_action = "memory_deleted"
        else:
            raise AdminValidationError("Unknown memory action")
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action=audit_action,
            target_type="memory",
            target_id=str(memory_id),
            target_user_id=owner.id,
            safe_summary=f"Memory {action} by administrator",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        return await self.get_memory(session, memory_id)

    async def archive_memory(self, session: AsyncSession, **kwargs: Any) -> AdminMemoryDetail:
        return await self._memory_owner_action(session, action="archive", **kwargs)

    async def reject_memory(self, session: AsyncSession, **kwargs: Any) -> AdminMemoryDetail:
        return await self._memory_owner_action(session, action="reject", **kwargs)

    async def delete_memory(self, session: AsyncSession, **kwargs: Any) -> None:
        await self._memory_owner_action(session, action="delete", **kwargs)

    # ── Tools ──────────────────────────────────────────────────────────────

    async def list_tools(self, session: AsyncSession) -> AdminToolListResponse:
        if self.tool_registry is None:
            return AdminToolListResponse(tools=[], total=0)
        await self.refresh_tool_overrides(session)
        stats = await self.repo.tool_execution_stats(session)
        configs = {c.tool_name: c for c in await self.repo.list_tool_configurations(session)}
        items: list[AdminToolSummary] = []
        for tool in self.tool_registry.list_all():
            stat = stats.get(tool.name, {})
            cfg = configs.get(tool.name)
            enabled = self.tool_registry.is_effectively_enabled(tool)
            items.append(
                AdminToolSummary(
                    name=tool.name,
                    category=tool.category,
                    version=tool.version,
                    description=tool.description,
                    enabled=enabled,
                    registry_enabled=bool(tool.enabled),
                    required_roles=[
                        r.value for r in sorted(tool.required_roles, key=lambda x: x.value)
                    ],
                    timeout_seconds=self.tool_registry.effective_timeout(tool),
                    confirmation_required=self.tool_registry.effective_confirmation_required(tool),
                    execution_count=int(stat.get("execution_count", 0)),
                    success_rate=stat.get("success_rate"),
                    average_duration_ms=stat.get("average_duration_ms"),
                    has_configuration=cfg is not None,
                )
            )
        return AdminToolListResponse(tools=items, total=len(items))

    async def update_tool(
        self,
        session: AsyncSession,
        *,
        actor: User,
        tool_name: str,
        enabled: bool | None = None,
        timeout_override: int | None = None,
        confirmation_required_override: bool | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminToolUpdateResponse:
        if self.tool_registry is None or not self.tool_registry.has(tool_name):
            raise AdminNotFoundError("Unknown tool")
        existing = await self.repo.get_tool_configuration(session, tool_name)
        new_enabled = (
            enabled
            if enabled is not None
            else (existing.enabled if existing else self.tool_registry.get(tool_name).enabled)
        )
        new_timeout = (
            timeout_override
            if timeout_override is not None
            else (existing.timeout_override if existing else None)
        )
        new_confirm = (
            confirmation_required_override
            if confirmation_required_override is not None
            else (existing.confirmation_required_override if existing else None)
        )
        await self.repo.upsert_tool_configuration(
            session,
            tool_name=tool_name,
            enabled=bool(new_enabled),
            timeout_override=new_timeout,
            confirmation_required_override=new_confirm,
            updated_by_user_id=actor.id,
        )
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="tool_configuration_updated",
            target_type="tool",
            target_id=tool_name,
            safe_summary=f"Tool '{tool_name}' configuration updated",
            metadata={
                "enabled": bool(new_enabled),
                "timeout_override": new_timeout,
                "confirmation_required_override": new_confirm,
            },
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        await self.refresh_tool_overrides(session)
        tools = await self.list_tools(session)
        match = next((t for t in tools.tools if t.name == tool_name), None)
        if match is None:
            raise AdminNotFoundError("Tool not found after update")
        return AdminToolUpdateResponse(tool=match)

    # ── Tool executions ────────────────────────────────────────────────────

    async def list_tool_executions(
        self, session: AsyncSession, **kwargs: Any
    ) -> AdminToolExecutionListResponse:
        limit = clamp_page_size(kwargs.pop("limit", 20))
        offset = max(0, int(kwargs.pop("offset", 0)))
        rows, total = await self.repo.list_tool_executions(
            session, limit=limit, offset=offset, **kwargs
        )
        items = [
            AdminToolExecutionSummary(
                id=execution.id,
                tool_name=execution.tool_name,
                user_id=owner.id,
                user_email=owner.email,
                conversation_id=execution.conversation_id,
                status=execution.status,
                started_at=execution.started_at,
                duration_ms=execution.duration_ms,
                error_code=execution.error_code,
                created_at=execution.created_at,
            )
            for execution, owner in rows
        ]
        return AdminToolExecutionListResponse(items=items, total=total, limit=limit, offset=offset)

    async def get_tool_execution(
        self, session: AsyncSession, execution_id: uuid.UUID
    ) -> AdminToolExecutionDetail:
        execution, owner = await self.repo.get_tool_execution(session, execution_id)
        base = AdminToolExecutionSummary(
            id=execution.id,
            tool_name=execution.tool_name,
            user_id=owner.id,
            user_email=owner.email,
            conversation_id=execution.conversation_id,
            status=execution.status,
            started_at=execution.started_at,
            duration_ms=execution.duration_ms,
            error_code=execution.error_code,
            created_at=execution.created_at,
        )
        return AdminToolExecutionDetail(
            **base.model_dump(),
            arguments_summary=_summary_from_mapping(execution.arguments_json),
            result_summary=_summary_from_mapping(execution.result_json),
            error_message=execution.error_message,
            correlation_id=execution.correlation_id,
            completed_at=execution.completed_at,
        )

    # ── Analytics ──────────────────────────────────────────────────────────

    async def get_analytics(
        self, session: AsyncSession, *, days: Literal[7, 30, 90] = 30
    ) -> AdminAnalyticsResponse:
        start, end = daterange_days(days)
        base = empty_analytics_points(start, end)
        # Reuse usage trend for conversations/messages/tools within window
        trend = await self.repo.usage_trend(session, days=days)
        series = merge_series(
            base,
            [
                (
                    point["date"],
                    {
                        "conversations": point["conversations"],
                        "messages": point["messages"],
                        "tool_executions": point["tool_executions"],
                    },
                )
                for point in trend
            ],
        )
        # New users by day
        from sqlalchemy import Date, cast, func, select

        from app.admin.repository import text_interval_days
        from app.models.user import User as UserModel

        user_rows = (
            await session.execute(
                select(cast(UserModel.created_at, Date).label("day"), func.count())
                .where(UserModel.created_at >= text_interval_days(days))
                .group_by("day")
            )
        ).all()
        series = merge_series(
            series,
            [(day, {"new_users": int(count)}) for day, count in user_rows],
        )
        from app.models.document import Document as DocModel

        doc_rows = (
            await session.execute(
                select(cast(DocModel.created_at, Date).label("day"), func.count())
                .where(DocModel.created_at >= text_interval_days(days))
                .group_by("day")
            )
        ).all()
        series = merge_series(
            series,
            [(day, {"document_uploads": int(count)}) for day, count in doc_rows],
        )

        points = [AdminAnalyticsPoint(**item) for item in series]
        totals: dict[str, int | float | None] = {
            "new_users": sum(p.new_users for p in points),
            "conversations": sum(p.conversations for p in points),
            "messages": sum(p.messages for p in points),
            "document_uploads": sum(p.document_uploads for p in points),
            "tool_executions": sum(p.tool_executions for p in points),
            "rag_queries": None,
            "ai_latency_ms": None,
            "retrieval_latency_ms": None,
            "first_token_latency_ms": None,
        }
        return AdminAnalyticsResponse(
            range_days=days,
            points=points,
            totals=totals,
            unavailable=[
                "rag_queries",
                "ai_latency_ms",
                "retrieval_latency_ms",
                "first_token_latency_ms",
                "token_costs",
            ],
            generated_at=datetime.now(UTC),
        )

    # ── Audit ──────────────────────────────────────────────────────────────

    async def list_audit(self, session: AsyncSession, **kwargs: Any) -> AdminAuditListResponse:
        limit = clamp_page_size(kwargs.pop("limit", 20))
        offset = max(0, int(kwargs.pop("offset", 0)))
        rows, total = await self.repo.list_audit_events(
            session, limit=limit, offset=offset, **kwargs
        )
        items = [
            AdminAuditEventSummary(
                id=event.id,
                actor_user_id=event.actor_user_id,
                actor_email=email,
                action=event.action,
                target_type=event.target_type,
                target_id=event.target_id,
                target_user_id=event.target_user_id,
                safe_summary=event.safe_summary,
                metadata_json=event.metadata_json,
                request_id=event.request_id,
                created_at=event.created_at,
            )
            for event, email in rows
        ]
        return AdminAuditListResponse(items=items, total=total, limit=limit, offset=offset)

    # ── System ─────────────────────────────────────────────────────────────

    async def get_system_health(self, session: AsyncSession) -> AdminSystemHealthResponse:
        components: list[AdminSystemComponentStatus] = [
            AdminSystemComponentStatus(name="backend", status="ok", message="Process alive")
        ]
        guidance: list[str] = []
        overall: Literal["ok", "degraded", "unavailable"] = "ok"

        if self.health_service is not None:
            ready, _code = await self.health_service.readiness()
            db_status = ready.checks.database.status
            redis_status = ready.checks.redis.status
            components.append(
                AdminSystemComponentStatus(
                    name="postgres",
                    status="ok" if db_status == "ok" else "unavailable",
                    message=ready.checks.database.message,
                    detail=self.settings.expected_database_identity,
                )
            )
            components.append(
                AdminSystemComponentStatus(
                    name="redis",
                    status="ok" if redis_status == "ok" else "unavailable",
                    message=ready.checks.redis.message,
                )
            )
            if db_status != "ok" or redis_status != "ok":
                overall = "unavailable"
                guidance.append("Check database and Redis readiness before serving traffic.")
        else:
            components.append(AdminSystemComponentStatus(name="postgres", status="unknown"))
            components.append(AdminSystemComponentStatus(name="redis", status="unknown"))

        components.extend(
            [
                AdminSystemComponentStatus(
                    name="ollama",
                    status="unknown",
                    message="Reachability checked via LLM status endpoint",
                    detail=self.settings.ollama_model,
                ),
                AdminSystemComponentStatus(
                    name="embedding_model",
                    status="unknown",
                    detail=self.settings.ollama_embedding_model,
                ),
                AdminSystemComponentStatus(
                    name="migrations",
                    status="unknown",
                    message="Use alembic current/heads for authoritative status",
                ),
                AdminSystemComponentStatus(
                    name="storage",
                    status="ok" if self.settings.document_upload_enabled else "degraded",
                    message="Document upload "
                    + ("enabled" if self.settings.document_upload_enabled else "disabled"),
                ),
                AdminSystemComponentStatus(
                    name="memory",
                    status="ok" if self.settings.memory_enabled else "degraded",
                ),
                AdminSystemComponentStatus(name="tools", status="ok"),
            ]
        )

        return AdminSystemHealthResponse(
            overall=overall,
            components=components,
            ai_configuration={
                "provider": self.settings.llm_provider,
                "chat_model": self.settings.ollama_model,
                "embedding_provider": self.settings.embedding_provider,
                "embedding_model": self.settings.ollama_embedding_model,
                "temperature": self.settings.llm_default_temperature,
                "max_output_tokens": self.settings.llm_max_output_tokens,
                "keep_alive": self.settings.ollama_keep_alive,
                "context_limit": self.settings.ollama_chat_num_ctx,
                "prediction_limit": self.settings.ollama_chat_num_predict,
                "tool_support": True,
                "streaming": True,
            },
            application={
                "name": self.settings.app_name,
                "version": self.settings.app_version,
                "environment": self.settings.app_env,
                "database_identity": self.settings.expected_database_identity,
            },
            refreshed_at=datetime.now(UTC),
            guidance=guidance,
        )

    # ── Settings ───────────────────────────────────────────────────────────

    async def get_settings(self, session: AsyncSession) -> AdminSettingsResponse:
        rows = await self.repo.list_platform_settings(session)
        overrides = {row.key: row.value_json for row in rows}
        effective = merge_effective_settings(self.settings, overrides)
        items: list[AdminSettingItem] = []
        for key in sorted(SAFE_SETTING_KEYS):
            source: Literal["default", "override", "runtime"] = (
                "override" if key in overrides else "default"
            )
            items.append(
                AdminSettingItem(
                    key=key,
                    value=effective.get(key),
                    source=source,
                    editable=True,
                )
            )
        return AdminSettingsResponse(
            settings=items,
            runtime=runtime_settings_snapshot(self.settings),
            unsafe_keys_blocked=sorted(UNSAFE_SETTING_KEYS),
        )

    async def update_settings(
        self,
        session: AsyncSession,
        *,
        actor: User,
        updates: dict[str, Any],
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminSettingsUpdateResponse:
        updated_keys: list[str] = []
        for key, raw in updates.items():
            if not is_safe_setting_key(key):
                raise AdminValidationError(f"Setting key '{key}' is not editable")
            if self.settings.is_production and key in {
                "registration_enabled",
                "tools_global_enabled",
            }:
                # Soft production guard — still allow display settings.
                pass
            value = validate_setting_value(key, raw)
            await self.repo.upsert_platform_setting(
                session,
                key=key,
                value=value,
                updated_by_user_id=actor.id,
            )
            updated_keys.append(key)
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="settings_updated",
            target_type="settings",
            target_id=None,
            safe_summary=f"Updated settings: {', '.join(updated_keys)}",
            metadata={"keys": updated_keys},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        settings = await self.get_settings(session)
        return AdminSettingsUpdateResponse(settings=settings.settings, updated_keys=updated_keys)
