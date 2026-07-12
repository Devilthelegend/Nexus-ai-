"""Vector store protocol and value types.

Tenant isolation is enforced by carrying ``workspace_id`` in every record's
payload and filtering on it at query time.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class VectorRecord:
    """A vector plus the payload used for filtering and provenance."""

    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchResult:
    """A single scored match returned from a similarity search."""

    id: str
    score: float
    payload: dict[str, Any]


@runtime_checkable
class VectorStore(Protocol):
    """Tenant-scoped similarity search over chunk embeddings."""

    async def ensure_ready(self, dimension: int) -> None:
        """Prepare backing storage (e.g. create the collection) if needed."""
        ...

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        """Insert or replace the given vectors."""
        ...

    async def search(
        self,
        embedding: Sequence[float],
        *,
        workspace_id: uuid.UUID,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Return the most similar vectors within a workspace."""
        ...

    async def delete_by_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Remove all vectors belonging to a document."""
        ...
