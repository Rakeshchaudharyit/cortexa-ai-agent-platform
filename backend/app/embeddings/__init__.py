"""Embeddings package."""

from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import create_embedding_provider

__all__ = ["EmbeddingProvider", "create_embedding_provider"]
