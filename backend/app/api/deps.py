"""Authentication and Phase 4 service FastAPI dependencies."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_exceptions import InvalidAccessTokenError
from app.core.config import Settings
from app.db.session import get_db_session
from app.memory.service import MemoryService
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import AuthService
from app.services.chat import ChatService
from app.services.conversations import ConversationService
from app.services.documents import DocumentService
from app.services.embeddings import EmbeddingService
from app.services.messages import MessageService
from app.services.password_reset import PasswordResetService
from app.services.rag import RagService
from app.services.retrieval import RetrievalService
from app.services.tools import ToolService

logger = logging.getLogger("cortexa.auth.deps")

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings_dep(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are not configured")
    return settings


def get_auth_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if isinstance(service, AuthService):
        return service
    settings = get_settings_dep(request)
    created = AuthService.from_settings(settings)
    request.app.state.auth_service = created
    return created


def get_password_reset_service(request: Request) -> PasswordResetService:
    service = getattr(request.app.state, "password_reset_service", None)
    if isinstance(service, PasswordResetService):
        return service
    settings = get_settings_dep(request)
    redis = getattr(request.app.state, "redis", None)
    created = PasswordResetService.from_settings(settings, redis=redis)
    request.app.state.password_reset_service = created
    return created


def get_document_service(request: Request) -> DocumentService:
    service = getattr(request.app.state, "document_service", None)
    if not isinstance(service, DocumentService):
        raise RuntimeError("Document service is not configured")
    return service


def get_retrieval_service(request: Request) -> RetrievalService:
    service = getattr(request.app.state, "retrieval_service", None)
    if not isinstance(service, RetrievalService):
        raise RuntimeError("Retrieval service is not configured")
    return service


def get_rag_service(request: Request) -> RagService:
    service = getattr(request.app.state, "rag_service", None)
    if not isinstance(service, RagService):
        raise RuntimeError("RAG service is not configured")
    return service


def get_embedding_service(request: Request) -> EmbeddingService:
    service = getattr(request.app.state, "embedding_service", None)
    if not isinstance(service, EmbeddingService):
        raise RuntimeError("Embedding service is not configured")
    return service


def get_conversation_service(request: Request) -> ConversationService:
    service = getattr(request.app.state, "conversation_service", None)
    if not isinstance(service, ConversationService):
        raise RuntimeError("Conversation service is not configured")
    return service


def get_chat_service(request: Request) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if not isinstance(service, ChatService):
        raise RuntimeError("Chat service is not configured")
    return service


def get_message_service(request: Request) -> MessageService:
    service = getattr(request.app.state, "message_service", None)
    if not isinstance(service, MessageService):
        raise RuntimeError("Message service is not configured")
    return service


def get_tool_service(request: Request) -> ToolService:
    service = getattr(request.app.state, "tool_service", None)
    if not isinstance(service, ToolService):
        raise RuntimeError("Tool service is not configured")
    return service


def get_memory_service(request: Request) -> MemoryService:
    service = getattr(request.app.state, "memory_service", None)
    if not isinstance(service, MemoryService):
        raise RuntimeError("Memory service is not configured")
    return service


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidAccessTokenError()
    token = credentials.credentials.strip()
    if not token:
        raise InvalidAccessTokenError()

    claims = auth_service.tokens.decode_access_token(token)
    user = await auth_service.get_user_by_id(session, claims.subject)
    if user is None:
        raise InvalidAccessTokenError()
    return user


async def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    return auth_service.ensure_active(user)


def require_role(*roles: UserRole) -> Callable[..., Any]:
    """Foundational role gate — admin UI is not implemented in Phase 3."""

    allowed = frozenset(roles)

    async def _dependency(
        user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if user.role not in allowed:
            from app.core.exceptions import AppError

            raise AppError(
                code="forbidden",
                message="Insufficient permissions",
                status_code=403,
            )
        return user

    return _dependency


CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
PasswordResetServiceDep = Annotated[PasswordResetService, Depends(get_password_reset_service)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]
RagServiceDep = Annotated[RagService, Depends(get_rag_service)]
EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]
ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]
ToolServiceDep = Annotated[ToolService, Depends(get_tool_service)]
MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]
