"""Qdrant-backed vector store adapter.

The ``qdrant-client`` dependency is imported lazily so the rest of the platform
runs offline with the in-memory store when Qdrant is not configured/installed.
Tenant isolation is enforced with a payload filter on ``workspace_id``.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from app.ai.vectorstore.base import SearchResult, VectorRecord


class QdrantVectorStore:
    """Vector store backed by a Qdrant collection."""

    def __init__(self, url: str, collection: str) -> None:
        from qdrant_client import AsyncQdrantClient

        self._client = AsyncQdrantClient(url=url)
        self._collection = collection

    async def ensure_ready(self, dimension: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not await self._client.collection_exists(self._collection):
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=dimension, distance=Distance.COSINE
                ),
            )

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=r.id, vector=r.vector, payload=r.payload)
            for r in records
        ]
        await self._client.upsert(self._collection, points=points)

    def _workspace_filter(self, workspace_id: uuid.UUID) -> Any:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchValue,
        )

        return Filter(
            must=[
                FieldCondition(
                    key="workspace_id",
                    match=MatchValue(value=str(workspace_id)),
                )
            ]
        )

    async def search(
        self,
        embedding: Sequence[float],
        *,
        workspace_id: uuid.UUID,
        limit: int = 5,
    ) -> list[SearchResult]:
        response = await self._client.query_points(
            self._collection,
            query=list(embedding),
            query_filter=self._workspace_filter(workspace_id),
            limit=limit,
            with_payload=True,
        )
        return [
            SearchResult(
                id=str(point.id),
                score=point.score,
                payload=point.payload or {},
            )
            for point in response.points
        ]

    async def delete_by_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )

        selector = FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="workspace_id",
                        match=MatchValue(value=str(workspace_id)),
                    ),
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_id)),
                    ),
                ]
            )
        )
        await self._client.delete(self._collection, points_selector=selector)
