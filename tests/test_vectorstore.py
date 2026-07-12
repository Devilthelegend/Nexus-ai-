"""Unit tests for the in-memory vector store and mock embedder."""

import uuid

from app.ai.embeddings.mock import MockEmbeddingProvider
from app.ai.vectorstore.base import VectorRecord
from app.ai.vectorstore.memory import InMemoryVectorStore


def _record(workspace_id: uuid.UUID, vector: list[float], text: str) -> VectorRecord:
    return VectorRecord(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={"workspace_id": str(workspace_id), "text": text},
    )


async def test_search_is_workspace_scoped() -> None:
    embedder = MockEmbeddingProvider(model="m", dimension=64)
    store = InMemoryVectorStore()
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()

    (vec_a,) = await embedder.embed(["alpha shared vocabulary"])
    (vec_b,) = await embedder.embed(["beta different words"])
    await store.upsert([_record(ws_a, vec_a, "a"), _record(ws_b, vec_b, "b")])

    (query,) = await embedder.embed(["alpha shared vocabulary"])
    results = await store.search(query, workspace_id=ws_a, limit=5)

    assert len(results) == 1
    assert results[0].payload["workspace_id"] == str(ws_a)


async def test_similar_text_ranks_first() -> None:
    embedder = MockEmbeddingProvider(model="m", dimension=128)
    store = InMemoryVectorStore()
    ws = uuid.uuid4()

    (near,) = await embedder.embed(["machine learning models and training"])
    (far,) = await embedder.embed(["completely unrelated cooking recipe"])
    near_rec = _record(ws, near, "near")
    far_rec = _record(ws, far, "far")
    await store.upsert([far_rec, near_rec])

    (query,) = await embedder.embed(["machine learning models"])
    results = await store.search(query, workspace_id=ws, limit=2)

    assert results[0].id == near_rec.id
    assert results[0].score >= results[1].score


async def test_delete_by_document_removes_only_target() -> None:
    store = InMemoryVectorStore()
    ws = uuid.uuid4()
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()

    def rec(doc_id: uuid.UUID) -> VectorRecord:
        return VectorRecord(
            id=str(uuid.uuid4()),
            vector=[1.0, 0.0],
            payload={
                "workspace_id": str(ws),
                "document_id": str(doc_id),
            },
        )

    await store.upsert([rec(doc_a), rec(doc_b)])
    await store.delete_by_document(ws, doc_a)

    results = await store.search([1.0, 0.0], workspace_id=ws, limit=10)
    assert len(results) == 1
    assert results[0].payload["document_id"] == str(doc_b)
