"""Vector store abstraction and implementations."""

from app.ai.vectorstore.base import SearchResult, VectorRecord, VectorStore
from app.ai.vectorstore.factory import get_vector_store

__all__ = [
    "SearchResult",
    "VectorRecord",
    "VectorStore",
    "get_vector_store",
]
