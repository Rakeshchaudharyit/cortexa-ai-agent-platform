"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.agents.definitions import create_default_agent_registry
from app.agents.orchestrator import AgentOrchestrator
from app.agents.repository import AgentRunRepository
from app.api.deps import get_current_active_user
from app.conversations.context import ConversationContextBuilder
from app.core.config import Settings, clear_settings_cache
from app.db.session import get_engine, get_session_factory, init_engine, reset_engine_state
from app.db.test_safety import (
    DEFAULT_TEST_IDENTITY,
    assert_database_url_is_safe_for_tests,
    assert_redis_url_is_safe_for_tests,
    assert_safe_test_session,
)
from app.documents.chunking import ChunkingConfig, ChunkingService
from app.documents.extraction import ExtractionService
from app.main import create_app
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.notifications.password_reset import create_password_reset_delivery
from app.providers.http import reset_http_client_state
from app.providers.redis import reset_redis_state
from app.schemas.health import DependencyCheck, ReadinessChecks, ReadinessResponse
from app.services.auth import AuthService
from app.services.chat import ChatService
from app.services.conversations import ConversationService
from app.services.documents import DocumentService
from app.services.embeddings import EmbeddingService
from app.services.health import HealthService
from app.services.llm import LLMService
from app.services.messages import MessageService
from app.services.password_reset import PasswordResetService
from app.services.rag import RagService
from app.services.retrieval import RetrievalService
from app.storage.local import LocalFilesystemStorage
from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tests.fakes.embeddings import FakeEmbeddingProvider
from tests.fakes.llm import FakeLLMProvider
from tests.fakes.redis import FakeRedis


async def _fake_title_generator(user_content: str, _assistant_content: str) -> str:
    snippet = user_content.strip().split()
    return " ".join(snippet[:6]) or "Untitled chat"


async def _fake_summarizer(existing: str | None, older_messages: list[Any]) -> str:
    roles = ",".join(m.role.value for m in older_messages[:5])
    base = existing or "Summary"
    return f"{base}|{len(older_messages)}|{roles}"[:500]


@pytest.fixture
def settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Settings]:
    """Isolated settings for unit tests (no real DB/Redis required)."""
    storage_root = tmp_path_factory.mktemp("document-storage")
    monkeypatch.setenv("APP_NAME", "Cortexa AI Knowledge Platform")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    monkeypatch.setenv("API_PREFIX", "/api/v1")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("BACKEND_PORT", "8000")
    # Isolated test database only — never cortexa_agent / development identity.
    monkeypatch.setenv("POSTGRES_HOST", os.environ.get("POSTGRES_HOST", "localhost"))
    monkeypatch.setenv("POSTGRES_PORT", os.environ.get("POSTGRES_PORT", "15433"))
    monkeypatch.setenv("POSTGRES_DB", "cortexa_agent_test")
    monkeypatch.setenv("POSTGRES_USER", os.environ.get("POSTGRES_USER", "cortexa"))
    monkeypatch.setenv(
        "POSTGRES_PASSWORD",
        os.environ.get("POSTGRES_PASSWORD", "local_test_only"),
    )
    # Prefer backend-test Compose DATABASE_URL when present; otherwise host-published
    # postgres-test on 15433. Never fall back to cortexa_agent.
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://cortexa:local_test_only@localhost:15433/cortexa_agent_test",
    )
    assert_database_url_is_safe_for_tests(database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("REDIS_HOST", os.environ.get("REDIS_HOST", "redis-test"))
    monkeypatch.setenv("REDIS_PORT", os.environ.get("REDIS_PORT", "6379"))
    monkeypatch.setenv("REDIS_DB", os.environ.get("REDIS_DB", "0"))
    redis_url = os.environ.get("REDIS_URL", "redis://redis-test:6379/0")
    # When running pytest on the host against published redis-test (16380), callers
    # must set REDIS_URL explicitly. Default assumes Compose service DNS.
    if "localhost" in redis_url or "127.0.0.1" in redis_url:
        # Host default: published redis-test port, non-colliding with dev 16379.
        if redis_url in {
            "redis://localhost:6379/0",
            "redis://127.0.0.1:6379/0",
        }:
            redis_url = "redis://127.0.0.1:16380/1"
    assert_redis_url_is_safe_for_tests(redis_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:13000,http://127.0.0.1:13000",
    )
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:13000")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-only-cortexa-jwt-secret-key-32chars-min",
    )
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "14")
    monkeypatch.setenv("AUTH_COOKIE_NAME", "cortexa_refresh")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("AUTH_COOKIE_PATH", "/api/v1/auth")
    monkeypatch.setenv("PASSWORD_MIN_LENGTH", "12")
    monkeypatch.setenv("PASSWORD_MAX_LENGTH", "128")
    monkeypatch.setenv("PASSWORD_RESET_ENABLED", "true")
    monkeypatch.setenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("PASSWORD_RESET_TOKEN_BYTES", "32")
    monkeypatch.setenv("PASSWORD_RESET_MAX_ACTIVE_TOKENS", "3")
    monkeypatch.setenv("PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv(
        "PASSWORD_RESET_FRONTEND_URL",
        "http://localhost:13000/reset-password",
    )
    monkeypatch.setenv("PASSWORD_RESET_DELIVERY_PROVIDER", "development")
    monkeypatch.setenv("PASSWORD_RESET_DEV_EXPOSE_TOKEN", "false")
    monkeypatch.setenv("PASSWORD_RESET_DEV_NOTICE_ENABLED", "true")
    monkeypatch.setenv("EXPECTED_APPLICATION_ID", "cortexa-ai-agent-platform")
    monkeypatch.setenv("EXPECTED_DATABASE_IDENTITY", DEFAULT_TEST_IDENTITY)
    monkeypatch.setenv("DATABASE_IDENTITY_CHECK_ENABLED", "true")
    monkeypatch.setenv("LEGACY_DB_MIGRATION_ALLOW_PRODUCTION", "false")
    monkeypatch.setenv("ADMIN_USER_CLI_ALLOW_PRODUCTION", "false")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("LLM_MAX_INPUT_CHARACTERS", "32000")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "256")
    monkeypatch.setenv("LLM_DEFAULT_TEMPERATURE", "0.2")
    # Phase 4 — documents / embeddings / RAG
    monkeypatch.setenv("DOCUMENT_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("DOCUMENT_STORAGE_PATH", str(storage_root))
    monkeypatch.setenv("DOCUMENT_MAX_FILE_SIZE_BYTES", "5242880")
    monkeypatch.setenv("DOCUMENT_ALLOWED_EXTENSIONS", ".txt,.md,.pdf,.docx")
    monkeypatch.setenv("DOCUMENT_MAX_TEXT_CHARACTERS", "500000")
    monkeypatch.setenv("DOCUMENT_MAX_CHUNKS", "500")
    monkeypatch.setenv("CHUNK_SIZE_CHARACTERS", "1200")
    monkeypatch.setenv("CHUNK_OVERLAP_CHARACTERS", "200")
    monkeypatch.setenv("CHUNK_MIN_CHARACTERS", "40")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "16")
    monkeypatch.setenv("EMBEDDING_REQUEST_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("EMBEDDING_MAX_INPUT_CHARACTERS", "8000")
    monkeypatch.setenv("RAG_DEFAULT_TOP_K", "5")
    monkeypatch.setenv("RAG_MAX_TOP_K", "20")
    monkeypatch.setenv("RAG_MIN_SIMILARITY", "0.0")
    monkeypatch.setenv("RAG_MAX_QUERY_CHARACTERS", "2000")
    monkeypatch.setenv("RAG_MAX_CONTEXT_CHARACTERS", "12000")
    monkeypatch.setenv("RAG_CITATION_EXCERPT_CHARACTERS", "280")
    # Phase 5 — conversations
    monkeypatch.setenv("CONVERSATION_MAX_HISTORY_MESSAGES", "8")
    monkeypatch.setenv("CONVERSATION_MAX_HISTORY_CHARACTERS", "4000")
    monkeypatch.setenv("CONVERSATION_MAX_CONTEXT_CHARACTERS", "8000")
    monkeypatch.setenv("CONVERSATION_SUMMARY_TRIGGER_MESSAGES", "6")
    monkeypatch.setenv("CONVERSATION_SUMMARY_MAX_CHARACTERS", "500")
    monkeypatch.setenv("CONVERSATION_TITLE_MAX_CHARACTERS", "80")
    monkeypatch.setenv("MESSAGE_MAX_CHARACTERS", "2000")
    monkeypatch.setenv("MESSAGE_MAX_RESPONSE_TOKENS", "256")
    monkeypatch.setenv("CHAT_DEFAULT_TEMPERATURE", "0.2")
    monkeypatch.setenv("CHAT_DEFAULT_TOP_K", "5")
    monkeypatch.setenv("CONVERSATION_SEARCH_MAX_RESULTS", "25")
    monkeypatch.setenv("CONVERSATION_LIST_DEFAULT_LIMIT", "20")
    monkeypatch.setenv("CONVERSATION_LIST_MAX_LIMIT", "50")
    monkeypatch.setenv("CITATION_EXCERPT_MAX_CHARACTERS", "280")
    monkeypatch.setenv("CONVERSATION_AUTO_TITLE_ENABLED", "true")
    monkeypatch.setenv("CONVERSATION_SUMMARY_ENABLED", "true")
    monkeypatch.setenv("CHAT_GENERAL_MODE_ENABLED", "true")
    clear_settings_cache()
    reset_engine_state()
    reset_redis_state()
    reset_http_client_state()
    resolved = Settings()
    yield resolved
    clear_settings_cache()
    reset_engine_state()
    reset_redis_state()
    reset_http_client_state()


class StubHealthService(HealthService):
    """Health service with injectable readiness outcomes for unit tests."""

    def __init__(
        self,
        settings: Settings,
        *,
        db_ok: bool = True,
        redis_ok: bool = True,
    ) -> None:
        super().__init__(settings=settings, engine=None, redis=None)
        self.db_ok = db_ok
        self.redis_ok = redis_ok

    async def readiness(self) -> tuple[ReadinessResponse, int]:
        checks = ReadinessChecks(
            database=DependencyCheck(
                status="ok" if self.db_ok else "error",
                message=None if self.db_ok else "Database unavailable",
            ),
            redis=DependencyCheck(
                status="ok" if self.redis_ok else "error",
                message=None if self.redis_ok else "Redis unavailable",
            ),
        )
        if self.db_ok and self.redis_ok:
            return ReadinessResponse(status="ready", checks=checks), 200
        return ReadinessResponse(status="not_ready", checks=checks), 503


def make_test_user(
    *,
    status: UserStatus = UserStatus.active,
    role: UserRole = UserRole.user,
    email: str = "user@example.com",
) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="not-a-real-hash",
        full_name="Test User",
        role=role,
        status=status,
        is_email_verified=False,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def fake_llm_provider() -> FakeLLMProvider:
    return FakeLLMProvider(model="qwen2.5:7b")


@pytest.fixture
def fake_embedding_provider(settings: Settings) -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(
        model=settings.ollama_embedding_model,
        dimension=settings.embedding_dimension,
    )


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Shared FakeRedis for development password-reset delivery tests."""
    return FakeRedis()


@pytest.fixture
def app(
    settings: Settings,
    fake_llm_provider: FakeLLMProvider,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_redis: FakeRedis,
) -> FastAPI:
    """Application with stubbed health/LLM/embedding services (no live dependencies)."""
    application = create_app(settings)
    application.state.health_service = StubHealthService(settings)
    application.state.llm_service = LLMService(settings=settings, provider=fake_llm_provider)
    application.state.auth_service = AuthService.from_settings(settings)
    application.state.redis = fake_redis
    delivery = create_password_reset_delivery(settings, redis=fake_redis)
    application.state.password_reset_delivery = delivery
    application.state.password_reset_service = PasswordResetService.from_settings(
        settings,
        delivery=delivery,
        redis=fake_redis,
    )
    application.state.embedding_provider = fake_embedding_provider
    application.state.embedding_service = EmbeddingService(
        settings=settings,
        provider=fake_embedding_provider,
    )

    # LLM generate/stream require an active user; override so non-auth LLM tests
    # remain independent of the database.
    async def _override_active_user() -> User:
        return make_test_user()

    application.dependency_overrides[get_current_active_user] = _override_active_user

    @application.get("/__test__/validate")
    async def _validate(value: int = Query(...)) -> dict[str, Any]:
        return {"value": value}

    @application.get("/__test__/boom")
    async def _boom() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="secret internal failure detail")

    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


_CLEANUP_STATEMENTS = (
    "DELETE FROM admin_audit_events",
    "DELETE FROM agent_run_events",
    "DELETE FROM agent_approvals",
    "DELETE FROM agent_handoffs",
    "DELETE FROM agent_tasks",
    "DELETE FROM agent_runs",
    "DELETE FROM tool_configurations",
    "DELETE FROM platform_settings",
    "DELETE FROM memory_audit_events",
    "DELETE FROM user_memories",
    "DELETE FROM user_memory_settings",
    "DELETE FROM tool_executions",
    "DELETE FROM message_citations",
    "DELETE FROM messages",
    "DELETE FROM conversations",
    "DELETE FROM document_chunks",
    "DELETE FROM documents",
    "DELETE FROM password_reset_tokens",
    "DELETE FROM refresh_sessions",
    "DELETE FROM users",
)


async def _cleanup_test_tables(session: Any) -> None:
    """Delete rows only after live connection proves we are on cortexa_agent_test."""
    await assert_safe_test_session(session, expected_identity=DEFAULT_TEST_IDENTITY)
    for statement in _CLEANUP_STATEMENTS:
        await session.execute(text(statement))
    await session.commit()


@pytest.fixture
async def db_engine(settings: Settings) -> AsyncIterator[None]:
    """Initialize DB engine against isolated test Postgres only."""
    assert_database_url_is_safe_for_tests(settings.database_url)
    assert_redis_url_is_safe_for_tests(settings.redis_url)
    init_engine(settings)
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")
    yield
    reset_engine_state()


@pytest.fixture
async def db_session(db_engine: None) -> AsyncIterator[Any]:
    _ = db_engine
    factory = get_session_factory()
    async with factory() as session:
        # Isolate integration tests without dropping schema. Hard-guarded.
        await _cleanup_test_tables(session)
        yield session
        await _cleanup_test_tables(session)


@pytest.fixture
def auth_app(
    settings: Settings,
    fake_llm_provider: FakeLLMProvider,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_redis: FakeRedis,
) -> FastAPI:
    """App for auth API tests — real auth deps, no active-user override."""
    application = create_app(settings)
    application.state.health_service = StubHealthService(settings)
    application.state.llm_service = LLMService(settings=settings, provider=fake_llm_provider)
    application.state.auth_service = AuthService.from_settings(settings)
    application.state.redis = fake_redis
    delivery = create_password_reset_delivery(settings, redis=fake_redis)
    application.state.password_reset_delivery = delivery
    application.state.password_reset_service = PasswordResetService.from_settings(
        settings,
        delivery=delivery,
        redis=fake_redis,
    )
    application.state.embedding_provider = fake_embedding_provider
    application.state.embedding_service = EmbeddingService(
        settings=settings,
        provider=fake_embedding_provider,
    )
    init_engine(settings)
    return application


@pytest.fixture
async def auth_client(auth_app: FastAPI, db_session: Any) -> AsyncIterator[AsyncClient]:
    _ = db_session  # ensure tables are cleaned before requests
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={},
    ) as async_client:
        yield async_client


def _wire_rag_services(
    application: FastAPI,
    *,
    settings: Settings,
    llm_provider: FakeLLMProvider,
    embedding_provider: FakeEmbeddingProvider,
    storage_root: Path,
) -> None:
    storage = LocalFilesystemStorage(root_path=str(storage_root))
    extraction_service = ExtractionService(settings)
    chunking_service = ChunkingService(
        ChunkingConfig(
            chunk_size=settings.chunk_size_characters,
            overlap=settings.chunk_overlap_characters,
            min_characters=settings.chunk_min_characters,
            max_chunks=settings.document_max_chunks,
        )
    )
    document_service = DocumentService(
        settings=settings,
        storage=storage,
        extraction_service=extraction_service,
        chunking_service=chunking_service,
        embedding_provider=embedding_provider,
    )
    retrieval_service = RetrievalService(
        settings=settings,
        embedding_provider=embedding_provider,
    )
    llm_service = LLMService(settings=settings, provider=llm_provider)
    embedding_service = EmbeddingService(
        settings=settings,
        provider=embedding_provider,
    )
    rag_service = RagService(
        settings=settings,
        retrieval_service=retrieval_service,
        llm_service=llm_service,
    )
    conversation_service = ConversationService(settings=settings)
    message_service = MessageService(
        settings=settings,
        conversation_service=conversation_service,
    )
    chat_service = ChatService(
        settings=settings,
        conversation_service=conversation_service,
        message_service=message_service,
        retrieval_service=retrieval_service,
        llm_service=llm_service,
        context_builder=ConversationContextBuilder(settings),
        title_generator=_fake_title_generator,
        summarizer=_fake_summarizer,
    )

    from app.memory.extractor import MemoryExtractor
    from app.memory.repository import MemoryRepository
    from app.memory.retrieval import MemoryRetriever
    from app.memory.service import MemoryService
    from app.services.tools import ToolService
    from app.tools.builtins import create_builtin_registry
    from app.tools.executor import ToolExecutor

    memory_repository = MemoryRepository(settings)
    memory_service = MemoryService(
        settings=settings,
        repository=memory_repository,
        embedding_provider=embedding_provider,
    )
    memory_retriever = MemoryRetriever(
        settings=settings,
        repository=memory_repository,
        embedding_provider=embedding_provider,
    )
    memory_extractor = MemoryExtractor(settings=settings, llm_service=llm_service)
    tool_registry = create_builtin_registry()
    tool_executor = ToolExecutor(
        registry=tool_registry,
        settings=settings,
        retrieval_service=retrieval_service,
        llm_service=llm_service,
        memory_service=memory_service,
    )
    tool_service = ToolService(registry=tool_registry)
    agent_orchestrator = AgentOrchestrator(
        settings=settings,
        llm_service=llm_service,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
    )
    agent_registry = create_default_agent_registry()
    agent_run_repository = AgentRunRepository(settings)
    from app.agents.multi_agent import MultiAgentService

    multi_agent_service = MultiAgentService(
        settings=settings,
        registry=agent_registry,
        repository=agent_run_repository,
        llm_service=llm_service,
        retrieval_service=retrieval_service,
        memory_service=memory_service,
        memory_retriever=memory_retriever,
        tool_executor=tool_executor,
        tool_registry=tool_registry,
    )
    # Keep tools off by default for existing chat compatibility tests.
    # Tool-focused suites enable AGENT_TOOLS_ENABLED and rebind chat_service.
    chat_service.agent_orchestrator = None
    chat_service.memory_service = memory_service
    chat_service.memory_retriever = memory_retriever
    chat_service.memory_extractor = memory_extractor
    chat_service.multi_agent_service = multi_agent_service

    application.state.health_service = StubHealthService(settings)
    application.state.auth_service = AuthService.from_settings(settings)
    fake_redis = FakeRedis()
    application.state.redis = fake_redis
    delivery = create_password_reset_delivery(settings, redis=fake_redis)
    application.state.password_reset_delivery = delivery
    application.state.password_reset_service = PasswordResetService.from_settings(
        settings,
        delivery=delivery,
        redis=fake_redis,
    )
    application.state.storage = storage
    application.state.extraction_service = extraction_service
    application.state.chunking_service = chunking_service
    application.state.document_service = document_service
    application.state.retrieval_service = retrieval_service
    application.state.llm_provider = llm_provider
    application.state.llm_service = llm_service
    application.state.embedding_provider = embedding_provider
    application.state.embedding_service = embedding_service
    application.state.rag_service = rag_service
    application.state.conversation_service = conversation_service
    application.state.message_service = message_service
    application.state.tool_registry = tool_registry
    application.state.tool_executor = tool_executor
    application.state.tool_service = tool_service
    application.state.memory_service = memory_service
    application.state.memory_retriever = memory_retriever
    application.state.memory_extractor = memory_extractor
    application.state.agent_orchestrator = agent_orchestrator
    application.state.agent_registry = agent_registry
    application.state.agent_run_repository = agent_run_repository
    application.state.multi_agent_service = multi_agent_service
    application.state.chat_service = chat_service


@pytest.fixture
def rag_app(
    settings: Settings,
    fake_llm_provider: FakeLLMProvider,
    tmp_path: Path,
) -> FastAPI:
    """App for document/RAG API tests — real auth, faked LLM/embeddings, temp storage."""
    fake_llm_provider.generate_content = (
        "Based on the provided context [1], Cortexa is a local-first agent platform."
    )
    embedding_provider = FakeEmbeddingProvider(
        model=settings.ollama_embedding_model,
        dimension=settings.embedding_dimension,
        identical_vectors=True,
    )
    application = create_app(settings)
    _wire_rag_services(
        application,
        settings=settings,
        llm_provider=fake_llm_provider,
        embedding_provider=embedding_provider,
        storage_root=tmp_path / "rag-documents",
    )
    init_engine(settings)
    # Expose providers for assertions (generate_calls, etc.).
    application.state.fake_llm_provider = fake_llm_provider
    application.state.fake_embedding_provider = embedding_provider
    return application


@pytest.fixture
async def rag_client(rag_app: FastAPI, db_session: Any) -> AsyncIterator[AsyncClient]:
    _ = db_session
    transport = ASGITransport(app=rag_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={},
    ) as async_client:
        yield async_client


@pytest.fixture
def chat_app(
    settings: Settings,
    fake_llm_provider: FakeLLMProvider,
    tmp_path: Path,
) -> FastAPI:
    """App for conversation/chat API tests with deterministic fakes."""
    fake_llm_provider.generate_content = (
        "Based on the provided context [1], Cortexa is a local-first agent platform."
    )
    embedding_provider = FakeEmbeddingProvider(
        model=settings.ollama_embedding_model,
        dimension=settings.embedding_dimension,
        identical_vectors=True,
    )
    application = create_app(settings)
    _wire_rag_services(
        application,
        settings=settings,
        llm_provider=fake_llm_provider,
        embedding_provider=embedding_provider,
        storage_root=tmp_path / "chat-documents",
    )
    init_engine(settings)
    application.state.fake_llm_provider = fake_llm_provider
    application.state.fake_embedding_provider = embedding_provider
    return application


@pytest.fixture
async def chat_client(chat_app: FastAPI, db_session: Any) -> AsyncIterator[AsyncClient]:
    _ = db_session
    transport = ASGITransport(app=chat_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={},
    ) as async_client:
        yield async_client
