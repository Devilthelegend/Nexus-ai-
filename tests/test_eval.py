"""Tests for the offline retrieval evaluation harness and its metrics."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.factory import get_embedding_provider
from app.ai.vectorstore.factory import _memory_store, get_vector_store
from app.eval import metrics, run_evaluation, sample_dataset

_AUTH = "/api/v1/auth"
_WS = "/api/v1/workspaces"
_PASSWORD = "s3cret-password"


@pytest.fixture(autouse=True)
def isolate_eval(tmp_path, monkeypatch):
    """Point uploads at a temp dir and reset the in-memory vector store."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    _memory_store.cache_clear()
    yield
    _memory_store.cache_clear()


def test_recall_at_k_counts_relevant_hits() -> None:
    assert metrics.recall_at_k(["a", "b", "c"], {"a", "c"}, k=3) == 1.0
    assert metrics.recall_at_k(["a", "b", "c"], {"a", "z"}, k=3) == 0.5
    assert metrics.recall_at_k([], {"a"}, k=3) == 0.0


def test_precision_at_k_counts_relevant_fraction() -> None:
    assert metrics.precision_at_k(["a", "b"], {"a"}, k=2) == 0.5
    assert metrics.precision_at_k(["a"], {"a"}, k=2) == 1.0


def test_reciprocal_rank_uses_first_relevant() -> None:
    assert metrics.reciprocal_rank(["x", "a"], {"a"}) == 0.5
    assert metrics.reciprocal_rank(["x", "y"], {"a"}) == 0.0


async def _workspace(client: AsyncClient, email: str) -> dict[str, object]:
    await client.post(f"{_AUTH}/register", json={"email": email, "password": _PASSWORD})
    login = await client.post(f"{_AUTH}/login", json={"email": email, "password": _PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    ws = await client.post(_WS, json={"name": "KB"}, headers=headers)
    return {"workspace_id": ws.json()["id"], "headers": headers}


async def test_recall_at_5_meets_threshold_on_golden_dataset(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ws = await _workspace(client, "eval-owner@example.com")
    dataset = sample_dataset()

    label_to_document_id: dict[str, str] = {}
    for doc in dataset.documents:
        files = {"file": (f"{doc.label}.txt", doc.text.encode(), "text/plain")}
        resp = await client.post(
            f"{_WS}/{ws['workspace_id']}/documents",
            files=files,
            headers=ws["headers"],
        )
        assert resp.json()["status"] == "indexed", resp.text
        label_to_document_id[doc.label] = resp.json()["id"]

    report = await run_evaluation(
        db_session,
        workspace_id=uuid.UUID(ws["workspace_id"]),
        dataset=dataset,
        label_to_document_id=label_to_document_id,
        embedder=get_embedding_provider(),
        store=get_vector_store(),
        k=5,
    )

    assert report.recall_at_k >= 0.85, report.per_case_recall
    assert report.mrr >= 0.85
