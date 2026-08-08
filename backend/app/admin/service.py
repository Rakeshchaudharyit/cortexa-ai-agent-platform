"""Enterprise administration application service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.analytics import daterange_days, empty_analytics_points, merge_series
from app.admin.audit import record_admin_action
from app.admin.deletion import AdminUserDeletionService
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
    AdminEvaluationTrendPoint,
    AdminFeedbackSummary,
    AdminKnowledgeHealth,
    AdminQualitySummary,
    AdminRankedMetric,
    AdminAuditEventSummary,
    AdminAuditListResponse,
    AdminConversationDeletionImpact,
    AdminConversationDetail,
    AdminConversationListResponse,
    AdminConversationSummary,
    AdminDashboardResponse,
    AdminDocumentDeletionImpact,
    AdminDocumentDetail,
    AdminDocumentListResponse,
    AdminDocumentSummary,
    AdminMemoryDeletionImpact,
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
    AdminUserDeleteResponse,
    AdminUserDeletionImpact,
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
from app.models.document import EMBEDDING_DIMENSION, Document
from app.models.conversation import Message, MessageCitation
from app.models.enums import (
    DocumentStatus,
    MemoryStatus,
    MessageRole,
    MessageStatus,
    UserRole,
    UserStatus,
)
from app.models.memory import UserMemory
from app.models.user import User
from app.models.evaluation import RagEvaluationRun
from app.models.feedback import MessageFeedback
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
        conversation_service: Any | None = None,
        health_service: Any | None = None,
        repository: AdminRepository | None = None,
    ) -> None:
        self.settings = settings
        self.auth_service = auth_service
        self.tool_registry = tool_registry
        self.document_service = document_service
        self.memory_service = memory_service
        self.conversation_service = conversation_service
        self.health_service = health_service
        self.repo = repository or AdminRepository()
        self.user_deletion = AdminUserDeletionService(
            auth_service=auth_service,
            document_service=document_service,
            repository=self.repo,
        )

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
                note="Token/cost analytics are unavailable for this data source",
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

    async def deactivate_user(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUserUpdateResponse:
        return await self.update_user(
            session,
            actor=actor,
            user_id=user_id,
            status=UserStatus.disabled,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def activate_user(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUserUpdateResponse:
        return await self.update_user(
            session,
            actor=actor,
            user_id=user_id,
            status=UserStatus.active,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get_user_deletion_impact(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
    ) -> AdminUserDeletionImpact:
        impact = await self.user_deletion.get_impact(session, actor=actor, user_id=user_id)
        return AdminUserDeletionImpact(
            user_id=impact.user_id,
            documents=impact.documents,
            document_chunks=impact.document_chunks,
            conversations=impact.conversations,
            messages=impact.messages,
            memories=impact.memories,
            refresh_sessions=impact.refresh_sessions,
            tool_executions=impact.tool_executions,
            can_delete=impact.can_delete,
            blocking_reason=impact.blocking_reason,
        )

    async def delete_user(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
        confirmation_email: str,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUserDeleteResponse:
        result = await self.user_deletion.delete_user(
            session,
            actor=actor,
            user_id=user_id,
            confirmation_email=confirmation_email,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return AdminUserDeleteResponse(
            user_id=result.user_id,
            email_fingerprint=result.email_fingerprint,
            documents_deleted=result.documents_deleted,
            document_chunks_deleted=result.document_chunks_deleted,
            conversations_deleted=result.conversations_deleted,
            messages_deleted=result.messages_deleted,
            memories_deleted=result.memories_deleted,
            refresh_sessions_revoked=result.refresh_sessions_revoked,
            tool_executions_anonymized=result.tool_executions_anonymized,
            storage_cleanup_failures=result.storage_cleanup_failures,
        )

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
        confirmation_filename: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        document, owner = await self.repo.get_document(session, document_id)
        confirmed = (
            confirmation_filename is not None
            and confirmation_filename.strip() == document.original_filename
        )
        if confirmation_filename is not None and not confirmed:
            raise AdminValidationError("Confirmation filename does not match the document")
        if self.document_service is None:
            raise AdminValidationError("Document service unavailable")
        filename = document.original_filename
        chunk_count = document.chunk_count
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
            metadata={"filename": filename[:128], "chunk_count": chunk_count},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            commit=True,
        )

    async def get_document_deletion_impact(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> AdminDocumentDeletionImpact:
        document, owner = await self.repo.get_document(session, document_id)
        return AdminDocumentDeletionImpact(
            document_id=document.id,
            filename=document.original_filename,
            owner_id=owner.id,
            owner_email=owner.email,
            chunk_count=document.chunk_count,
            has_stored_file=bool(document.storage_key),
            can_delete=True,
            blocking_reason=None,
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

    async def get_conversation_deletion_impact(
        self, session: AsyncSession, conversation_id: uuid.UUID
    ) -> AdminConversationDeletionImpact:
        data = await self.repo.get_conversation(session, conversation_id)
        conv = data["conversation"]
        owner: User = data["owner"]
        citations = await self.repo.conversation_citation_count(session, conversation_id)
        linked_memories = await self.repo.conversation_linked_memory_count(session, conversation_id)
        return AdminConversationDeletionImpact(
            conversation_id=conv.id,
            title=conv.title,
            owner_id=owner.id,
            owner_email=owner.email,
            messages=data["message_count"],
            citations=citations,
            tool_executions=data["tool_execution_count"],
            linked_memories=linked_memories,
            can_delete=True,
            blocking_reason=None,
        )

    async def archive_conversation(
        self,
        session: AsyncSession,
        *,
        actor: User,
        conversation_id: uuid.UUID,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminConversationDetail:
        if self.conversation_service is None:
            raise AdminValidationError("Conversation service unavailable")
        data = await self.repo.get_conversation(session, conversation_id)
        owner: User = data["owner"]
        await self.conversation_service.archive_conversation(session, owner, conversation_id)
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="conversation_archived",
            target_type="conversation",
            target_id=str(conversation_id),
            target_user_id=owner.id,
            safe_summary="Conversation archived by administrator",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        return await self.get_conversation(session, conversation_id)

    async def delete_conversation(
        self,
        session: AsyncSession,
        *,
        actor: User,
        conversation_id: uuid.UUID,
        confirm: bool = False,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        if not confirm:
            raise AdminValidationError("Confirmation required to permanently delete a conversation")
        if self.conversation_service is None:
            raise AdminValidationError("Conversation service unavailable")
        data = await self.repo.get_conversation(session, conversation_id)
        owner: User = data["owner"]
        message_count = data["message_count"]
        await self.conversation_service.delete_conversation(session, owner, conversation_id)
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="conversation_permanently_deleted",
            target_type="conversation",
            target_id=str(conversation_id),
            target_user_id=owner.id,
            safe_summary="Conversation permanently deleted by administrator",
            metadata={"messages": message_count},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()

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

    async def get_memory_deletion_impact(
        self, session: AsyncSession, memory_id: uuid.UUID
    ) -> AdminMemoryDeletionImpact:
        memory, owner = await self.repo.get_memory(session, memory_id)
        title = memory.title if memory.status != MemoryStatus.deleted else "[deleted]"
        return AdminMemoryDeletionImpact(
            memory_id=memory.id,
            title=title,
            owner_id=owner.id,
            owner_email=owner.email,
            status=memory.status,
            has_embedding=memory.embedding is not None,
            can_delete=memory.status != MemoryStatus.deleted,
            blocking_reason=(
                "Memory is already deleted/redacted"
                if memory.status == MemoryStatus.deleted
                else None
            ),
        )

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

    async def reset_tool_configuration(
        self,
        session: AsyncSession,
        *,
        actor: User,
        tool_name: str,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminToolUpdateResponse:
        if self.tool_registry is None or not self.tool_registry.has(tool_name):
            raise AdminNotFoundError("Unknown tool")
        deleted = await self.repo.delete_tool_configuration(session, tool_name)
        if not deleted:
            raise AdminNotFoundError("No persisted tool configuration override to reset")
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="tool_configuration_reset",
            target_type="tool",
            target_id=tool_name,
            safe_summary=f"Tool '{tool_name}' configuration reset to registry defaults",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        await self.refresh_tool_overrides(session)
        tools = await self.list_tools(session)
        match = next((t for t in tools.tools if t.name == tool_name), None)
        if match is None:
            raise AdminNotFoundError("Tool not found after reset")
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
                user_id=owner.id if owner is not None else None,
                user_email=owner.email if owner is not None else None,
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
            user_id=owner.id if owner is not None else None,
            user_email=owner.email if owner is not None else None,
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
        """Return bounded, content-free platform and AI observability metrics."""
        start, end = daterange_days(days)
        base = empty_analytics_points(start, end)
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

        from sqlalchemy import Date, cast, func, select
        from app.admin.repository import text_interval_days
        from app.models.user import User as UserModel
        from app.models.document import Document as DocModel

        user_rows = (
            await session.execute(
                select(cast(UserModel.created_at, Date).label("day"), func.count())
                .where(UserModel.created_at >= text_interval_days(days))
                .group_by("day")
            )
        ).all()
        series = merge_series(series, [(day, {"new_users": int(count)}) for day, count in user_rows])

        doc_rows = (
            await session.execute(
                select(cast(DocModel.created_at, Date).label("day"), func.count())
                .where(DocModel.created_at >= text_interval_days(days))
                .group_by("day")
            )
        ).all()
        series = merge_series(series, [(day, {"document_uploads": int(count)}) for day, count in doc_rows])

        message_rows = (
            await session.execute(
                select(
                    Message.created_at, Message.status, Message.grounded, Message.latency_ms,
                    Message.total_tokens, Message.finish_reason, Message.error_code,
                    Message.provider, Message.model, Message.message_metadata,
                ).where(
                    Message.created_at >= start,
                    Message.created_at <= end,
                    Message.role == MessageRole.assistant,
                    Message.is_active.is_(True),
                )
            )
        ).all()

        by_day = {item["date"]: item for item in series}
        providers: dict[str, int] = {}
        models: dict[str, int] = {}
        latency_values: list[float] = []
        retrieval_values: list[float] = []
        generation_values: list[float] = []
        first_token_values: list[float] = []

        for row in message_rows:
            day = row.created_at.date().isoformat()
            point = by_day.get(day)
            if point is None:
                continue
            metadata = row.message_metadata if isinstance(row.message_metadata, dict) else {}
            timing = metadata.get("rag_timing") if isinstance(metadata.get("rag_timing"), dict) else {}
            citation_count = int(timing.get("citation_count") or 0)
            retrieval_count = int(timing.get("retrieved_chunk_count") or 0)
            is_rag = bool(row.grounded is not None or retrieval_count or row.finish_reason == "no_context")
            failed = bool(row.status == MessageStatus.failed or row.error_code)
            no_answer = bool(row.finish_reason == "no_context")

            if is_rag:
                point["rag_queries"] += 1
            point["failed_responses" if failed else "successful_responses"] += 1
            if no_answer:
                point["no_answer_responses"] += 1
            point["citation_count"] += citation_count
            point["total_tokens"] += int(row.total_tokens or 0)

            def add_metric(key: str, destination: list[float]) -> None:
                value = timing.get(key)
                if isinstance(value, (int, float)):
                    destination.append(float(value))

            if row.latency_ms is not None:
                latency_values.append(float(row.latency_ms))
            add_metric("retrieval_ms", retrieval_values)
            add_metric("model_total_ms", generation_values)
            add_metric("model_time_to_first_token_ms", first_token_values)

            provider = row.provider or "unknown"
            model = row.model or "unknown"
            providers[provider] = providers.get(provider, 0) + 1
            models[model] = models.get(model, 0) + 1

        def average(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 2) if values else None

        # Daily averages use only values recorded on that day.
        for day, point in by_day.items():
            day_rows = [row for row in message_rows if row.created_at.date().isoformat() == day]
            day_latency: list[float] = []
            day_retrieval: list[float] = []
            day_generation: list[float] = []
            day_first_token: list[float] = []
            for row in day_rows:
                if row.latency_ms is not None:
                    day_latency.append(float(row.latency_ms))
                metadata = row.message_metadata if isinstance(row.message_metadata, dict) else {}
                timing = metadata.get("rag_timing") if isinstance(metadata.get("rag_timing"), dict) else {}
                for key, dest in (
                    ("retrieval_ms", day_retrieval),
                    ("model_total_ms", day_generation),
                    ("model_time_to_first_token_ms", day_first_token),
                ):
                    value = timing.get(key)
                    if isinstance(value, (int, float)):
                        dest.append(float(value))
            point["ai_latency_ms"] = average(day_latency)
            point["retrieval_latency_ms"] = average(day_retrieval)
            point["generation_latency_ms"] = average(day_generation)
            point["first_token_latency_ms"] = average(day_first_token)

        points = [AdminAnalyticsPoint(**item) for item in series]
        successful = sum(p.successful_responses for p in points)
        failed = sum(p.failed_responses for p in points)
        total_responses = successful + failed
        totals: dict[str, int | float | None] = {
            "new_users": sum(p.new_users for p in points),
            "conversations": sum(p.conversations for p in points),
            "messages": sum(p.messages for p in points),
            "document_uploads": sum(p.document_uploads for p in points),
            "tool_executions": sum(p.tool_executions for p in points),
            "rag_queries": sum(p.rag_queries for p in points),
            "successful_responses": successful,
            "failed_responses": failed,
            "success_rate": round(successful / total_responses, 4) if total_responses else None,
            "no_answer_responses": sum(p.no_answer_responses for p in points),
            "citation_count": sum(p.citation_count for p in points),
            "total_tokens": sum(p.total_tokens for p in points),
            "ai_latency_ms": average(latency_values),
            "retrieval_latency_ms": average(retrieval_values),
            "generation_latency_ms": average(generation_values),
            "first_token_latency_ms": average(first_token_values),
        }
        # Enterprise quality roll-up from evaluations, feedback, success, and citation coverage.
        feedback_rows = (await session.execute(
            select(MessageFeedback.sentiment, MessageFeedback.status, func.count())
            .where(MessageFeedback.created_at >= start, MessageFeedback.created_at <= end)
            .group_by(MessageFeedback.sentiment, MessageFeedback.status)
        )).all()
        feedback_total = sum(int(count) for _sentiment, _status, count in feedback_rows)
        helpful = sum(int(count) for sentiment, _status, count in feedback_rows if sentiment == "helpful")
        not_helpful = sum(int(count) for sentiment, _status, count in feedback_rows if sentiment == "not_helpful")
        open_reviews = sum(int(count) for _sentiment, status, count in feedback_rows if status == "open")
        helpful_rate = round(helpful / feedback_total, 4) if feedback_total else None

        latest_eval = (await session.execute(
            select(RagEvaluationRun)
            .where(RagEvaluationRun.status == "completed")
            .order_by(RagEvaluationRun.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        evaluation_score = round(float(latest_eval.average_score), 2) if latest_eval else None
        eval_rows = (await session.execute(
            select(RagEvaluationRun.created_at, RagEvaluationRun.average_score,
                   RagEvaluationRun.passed_cases, RagEvaluationRun.total_cases)
            .where(RagEvaluationRun.status == "completed", RagEvaluationRun.created_at >= start)
            .order_by(RagEvaluationRun.created_at.asc())
            .limit(30)
        )).all()
        evaluation_trend = [
            AdminEvaluationTrendPoint(
                date=created.date().isoformat(),
                average_score=round(float(score), 2),
                pass_rate=round((passed / total) * 100, 2) if total else 0.0,
                total_cases=int(total),
            )
            for created, score, passed, total in eval_rows
        ]

        rag_queries = int(totals["rag_queries"] or 0)
        cited_rag_responses = sum(1 for row in message_rows if isinstance(row.message_metadata, dict) and int(((row.message_metadata.get("rag_timing") or {}).get("citation_count") or 0)) > 0)
        citation_coverage = round((cited_rag_responses / rag_queries) * 100, 2) if rag_queries else None
        success_score = round(float(totals["success_rate"]) * 100, 2) if totals["success_rate"] is not None else None
        feedback_score = round(helpful_rate * 100, 2) if helpful_rate is not None else None
        components = [(evaluation_score, 0.35), (feedback_score, 0.25), (success_score, 0.20), (citation_coverage, 0.20)]
        available_components = [(value, weight) for value, weight in components if value is not None]
        quality_score = round(sum(value * weight for value, weight in available_components) / sum(weight for _value, weight in available_components), 1) if available_components else None
        quality_label = "Insufficient data" if quality_score is None else ("Excellent" if quality_score >= 90 else "Good" if quality_score >= 75 else "Needs attention" if quality_score >= 60 else "At risk")

        doc_counts = dict((str(status), int(count)) for status, count in (await session.execute(
            select(Document.status, func.count()).group_by(Document.status)
        )).all())
        total_documents = sum(doc_counts.values())
        zero_chunks = int((await session.execute(select(func.count()).select_from(Document).where(Document.chunk_count == 0))).scalar_one())
        stale_cutoff = datetime.now(UTC) - timedelta(days=90)
        stale_documents = int((await session.execute(select(func.count()).select_from(Document).where(Document.updated_at < stale_cutoff))).scalar_one())
        duplicate_groups = int((await session.execute(
            select(func.count()).select_from(
                select(Document.checksum_sha256).group_by(Document.checksum_sha256).having(func.count() > 1).subquery()
            )
        )).scalar_one())
        ready_documents = doc_counts.get(DocumentStatus.ready.value, 0)
        unhealthy = doc_counts.get(DocumentStatus.failed.value, 0) + zero_chunks + stale_documents
        knowledge_score = round(max(0.0, 100.0 - (unhealthy / max(total_documents, 1)) * 100), 1) if total_documents else None

        top_doc_rows = (await session.execute(
            select(MessageCitation.filename, func.count().label("uses"))
            .where(MessageCitation.created_at >= start, MessageCitation.created_at <= end)
            .group_by(MessageCitation.filename)
            .order_by(func.count().desc())
            .limit(8)
        )).all()
        top_documents = [AdminRankedMetric(label=filename, value=int(uses), secondary="citations") for filename, uses in top_doc_rows]
        top_models = [AdminRankedMetric(label=model, value=count, secondary="responses") for model, count in sorted(models.items(), key=lambda item: item[1], reverse=True)[:8]]

        return AdminAnalyticsResponse(
            range_days=days,
            points=points,
            totals=totals,
            quality=AdminQualitySummary(
                score=quality_score, evaluation_score=evaluation_score, feedback_score=feedback_score,
                success_score=success_score, citation_coverage_score=citation_coverage, label=quality_label,
            ),
            knowledge_health=AdminKnowledgeHealth(
                total_documents=total_documents, ready_documents=ready_documents,
                pending_documents=doc_counts.get(DocumentStatus.pending.value, 0),
                processing_documents=doc_counts.get(DocumentStatus.processing.value, 0),
                failed_documents=doc_counts.get(DocumentStatus.failed.value, 0),
                zero_chunk_documents=zero_chunks, stale_documents=stale_documents,
                duplicate_content_groups=duplicate_groups, health_score=knowledge_score,
            ),
            feedback=AdminFeedbackSummary(
                total=feedback_total, helpful=helpful, not_helpful=not_helpful,
                open_reviews=open_reviews, helpful_rate=helpful_rate,
            ),
            top_documents=top_documents, top_models=top_models, evaluation_trend=evaluation_trend,
            unavailable=["token_costs"],
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

    async def reset_setting(
        self,
        session: AsyncSession,
        *,
        actor: User,
        key: str,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminSettingsUpdateResponse:
        if not is_safe_setting_key(key):
            raise AdminValidationError(f"Setting key '{key}' is not editable")
        deleted = await self.repo.delete_platform_setting(session, key)
        if not deleted:
            raise AdminNotFoundError("No database override exists for this setting")
        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="settings_reset",
            target_type="settings",
            target_id=key,
            safe_summary=f"Reset setting '{key}' to environment/default configuration",
            metadata={"key": key},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        settings = await self.get_settings(session)
        return AdminSettingsUpdateResponse(settings=settings.settings, updated_keys=[key])
