"""Application lifespan: DB engine, Redis client, HTTP client, LLM/embedding/RAG services."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, init_engine
from app.documents.chunking import ChunkingConfig, ChunkingService
from app.documents.extraction import ExtractionService
from app.embeddings.factory import create_embedding_provider
from app.llm.factory import create_llm_provider
from app.providers.http import close_http_client, init_http_client
from app.providers.redis import close_redis, init_redis
from app.services.auth import AuthService
from app.services.documents import DocumentService
from app.services.embeddings import EmbeddingService
from app.services.health import HealthService
from app.services.llm import LLMService
from app.services.rag import RagService
from app.services.retrieval import RetrievalService
from app.storage.local import LocalFilesystemStorage

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

    app.state.settings = settings
    app.state.engine = engine
    app.state.redis = redis
    app.state.http_client = http_client
    app.state.llm_provider = llm_provider
    app.state.llm_service = llm_service
    app.state.auth_service = auth_service
    app.state.storage = storage
    app.state.embedding_provider = embedding_provider
    app.state.extraction_service = extraction_service
    app.state.chunking_service = chunking_service
    app.state.document_service = document_service
    app.state.retrieval_service = retrieval_service
    app.state.embedding_service = embedding_service
    app.state.rag_service = rag_service
    app.state.health_service = HealthService(
        settings=settings,
        engine=engine,
        redis=redis,
    )

    try:
        yield
    finally:
        logger.info("shutting_down_application")
        await close_http_client()
        await close_redis()
        await dispose_engine()
