"""Embedding provider protocol.

Providers turn text into dense vectors. The protocol keeps the ingestion and
retrieval code independent of any specific vendor (OpenAI, local models, mock).
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """A source of dense embeddings for text."""

    @property
    def model(self) -> str:
        """Identifier of the embedding model (recorded for provenance)."""
        ...

    @property
    def dimension(self) -> int:
        """Dimensionality of the produced vectors."""
        ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...
