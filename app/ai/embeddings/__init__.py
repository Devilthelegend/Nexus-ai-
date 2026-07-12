"""Embedding provider abstraction and implementations."""

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.factory import get_embedding_provider

__all__ = ["EmbeddingProvider", "get_embedding_provider"]
