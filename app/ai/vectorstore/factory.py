"""Select a vector store from application settings.

The in-memory backend is a process-wide singleton so that data indexed during a
request remains queryable by later requests within the same process.
"""

from functools import lru_cache

from app.ai.vectorstore.base import VectorStore
from app.ai.vectorstore.memory import InMemoryVectorStore
from app.core.config import Settings, get_settings


@lru_cache(maxsize=1)
def _memory_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


def get_vector_store(settings: Settings | None = None) -> VectorStore:
    """Return the configured vector store implementation."""
    settings = settings or get_settings()
    backend = settings.vector_backend

    if backend == "memory":
        return _memory_store()
    if backend == "qdrant":
        from app.ai.vectorstore.qdrant import QdrantVectorStore

        return QdrantVectorStore(
            url=settings.qdrant_url, collection=settings.qdrant_collection
        )

    raise ValueError(f"Unsupported vector backend: {backend!r}")
