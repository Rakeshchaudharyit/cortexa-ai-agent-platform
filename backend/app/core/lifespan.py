"""Application lifespan: DB engine, Redis client, HTTP client, LLM/embedding/RAG services."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.admin.service import AdminService
from app.agents.definitions import create_default_agent_registry
from app.agents.multi_agent import MultiAgentService
from app.agents.orchestrator import AgentOrchestrator
from app.agents.repository import AgentRunRepository
from app.conversations.context import ConversationContextBuilder
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, init_engine
from app.documents.chunking import ChunkingConfig, ChunkingService
from app.documents.extraction import ExtractionService
from app.embeddings.factory import create_embedding_provider
from app.llm.factory import create_llm_provider
from app.memory.extractor import MemoryExtractor
from app.memory.repository import MemoryRepository
from app.memory.retrieval import MemoryRetriever
from app.memory.service import MemoryService
from app.notifications.password_reset import create_password_reset_delivery
from app.providers.http import close_http_client, init_http_client
from app.providers.redis import close_redis, init_redis
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
from app.services.tools import ToolService
from app.storage.local import LocalFilesystemStorage
from app.tools.builtins import create_builtin_registry
from app.tools.executor import ToolExecutor

logger = logging.getLogger("cortexa.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = getattr(app.state, "settings", None) or get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "starting_application name=%s version=%s env=%s llm_provider=%s embedding_provider=%s",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.llm_provider,
        settings.embedding_provider,
    )

    engine = init_engine(settings)
    redis = await init_redis(settings)
    http_client = await init_http_client(settings)
    llm_provider = create_llm_provider(settings, http_client)
    llm_service = LLMService(settings=settings, provider=llm_provider)
    auth_service = AuthService.from_settings(settings)
    password_reset_delivery = create_password_reset_delivery(settings, redis=redis)
    password_reset_service = PasswordResetService.from_settings(
        settings,
        delivery=password_reset_delivery,
        redis=redis,
    )

    storage = LocalFilesystemStorage(root_path=settings.document_storage_path)
    embedding_provider = create_embedding_provider(settings, http_client)
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
    tool_registry = create_builtin_registry()
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
    memory_extractor = MemoryExtractor(
        settings=settings,
        llm_service=llm_service,
    )
    tool_executor = ToolExecutor(
        registry=tool_registry,
        settings=settings,
        retrieval_service=retrieval_service,
        llm_service=llm_service,
        memory_service=memory_service,
    )
    tool_service = ToolService(registry=tool_registry)
    agent_registry = create_default_agent_registry()
    agent_run_repository = AgentRunRepository(settings)
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
    agent_orchestrator = AgentOrchestrator(
        settings=settings,
        llm_service=llm_service,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
    )
    chat_service = ChatService(
        settings=settings,
        conversation_service=conversation_service,
        message_service=message_service,
        retrieval_service=retrieval_service,
        llm_service=llm_service,
        context_builder=ConversationContextBuilder(settings),
        agent_orchestrator=agent_orchestrator,
        memory_service=memory_service,
        memory_retriever=memory_retriever,
        memory_extractor=memory_extractor,
        multi_agent_service=multi_agent_service,
    )
    health_service = HealthService(
        settings=settings,
        engine=engine,
        redis=redis,
    )
    admin_service = AdminService(
        settings=settings,
        auth_service=auth_service,
        tool_registry=tool_registry,
        document_service=document_service,
        memory_service=memory_service,
        conversation_service=conversation_service,
        health_service=health_service,
    )

    # Apply persisted tool configuration overrides when the database is reachable.
    try:
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            await admin_service.refresh_tool_overrides(session)
    except Exception:  # noqa: BLE001
        logger.warning("admin_tool_overrides_load_failed")

    app.state.settings = settings
    app.state.engine = engine
    app.state.redis = redis
    app.state.http_client = http_client
    app.state.llm_provider = llm_provider
    app.state.llm_service = llm_service
    app.state.auth_service = auth_service
    app.state.password_reset_delivery = password_reset_delivery
    app.state.password_reset_service = password_reset_service
    app.state.storage = storage
    app.state.embedding_provider = embedding_provider
    app.state.extraction_service = extraction_service
    app.state.chunking_service = chunking_service
    app.state.document_service = document_service
    app.state.retrieval_service = retrieval_service
    app.state.embedding_service = embedding_service
    app.state.rag_service = rag_service
    app.state.conversation_service = conversation_service
    app.state.message_service = message_service
    app.state.tool_registry = tool_registry
    app.state.tool_executor = tool_executor
    app.state.tool_service = tool_service
    app.state.memory_service = memory_service
    app.state.memory_retriever = memory_retriever
    app.state.memory_extractor = memory_extractor
    app.state.agent_registry = agent_registry
    app.state.agent_run_repository = agent_run_repository
    app.state.multi_agent_service = multi_agent_service
    app.state.agent_orchestrator = agent_orchestrator
    app.state.chat_service = chat_service
    app.state.health_service = health_service
    app.state.admin_service = admin_service

    try:
        yield
    finally:
        logger.info("shutting_down_application")
        await close_http_client()
        await close_redis()
        await dispose_engine()
