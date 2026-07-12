"""In-memory vector store: offline default for tests and local development.

Implements cosine similarity with workspace-scoped payload filtering, mirroring
the semantics of the Qdrant adapter so call sites are interchangeable.
"""

import math
import uuid
from collections.abc import Sequence

from app.ai.vectorstore.base import SearchResult, VectorRecord


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Process-local vector index. Not persistent; intended for dev/test."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    async def ensure_ready(self, dimension: int) -> None:
        return None

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        for record in records:
            self._records[record.id] = record

    async def search(
        self,
        embedding: Sequence[float],
        *,
        workspace_id: uuid.UUID,
        limit: int = 5,
    ) -> list[SearchResult]:
        scoped = [
            record
            for record in self._records.values()
            if record.payload.get("workspace_id") == str(workspace_id)
        ]
        scored = [
            SearchResult(
                id=record.id,
                score=_cosine(embedding, record.vector),
                payload=record.payload,
            )
            for record in scoped
        ]
        scored.sort(key=lambda result: result.score, reverse=True)
        return scored[:limit]

    async def delete_by_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        to_delete = [
            key
            for key, record in self._records.items()
            if record.payload.get("workspace_id") == str(workspace_id)
            and record.payload.get("document_id") == str(document_id)
        ]
        for key in to_delete:
            del self._records[key]
