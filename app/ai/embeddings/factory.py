"""Select an embedding provider from application settings."""

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.mock import MockEmbeddingProvider
from app.core.config import Settings, get_settings


def get_embedding_provider(
    settings: Settings | None = None,
) -> EmbeddingProvider:
    """Return the configured embedding provider.

    Only the offline ``mock`` provider ships today; real providers (e.g. OpenAI)
    are added here behind the same protocol without touching call sites.
    """
    settings = settings or get_settings()
    provider = settings.embedding_provider.lower()

    if provider == "mock":
        return MockEmbeddingProvider(
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )

    raise ValueError(f"Unsupported embedding provider: {provider!r}")
