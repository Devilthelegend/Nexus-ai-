"""Tests for the workspace-scoped semantic cache and its RAG integration."""

import uuid

import pytest
from httpx import AsyncClient

from app.ai.embeddings.factory import get_embedding_provider
from app.ai.vectorstore.factory import _memory_store
from app.services.semantic_cache import CachedAnswer, SemanticCache, get_semantic_cache

_AUTH = "/api/v1/auth"
_WS = "/api/v1/workspaces"
_PASSWORD = "s3cret-password"


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """Temp uploads and a clean vector store + semantic cache per test."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    _memory_store.cache_clear()
    get_semantic_cache().clear()
    yield
    _memory_store.cache_clear()
    get_semantic_cache().clear()


def test_lookup_returns_hit_above_threshold() -> None:
    cache = SemanticCache()
    wid = uuid.uuid4()
    cache.store(wid, [1.0, 0.0, 0.0], CachedAnswer("cached", []))

    hit = cache.lookup(wid, [1.0, 0.0, 0.0], threshold=0.9)
    assert hit is not None
    assert hit.answer == "cached"


def test_lookup_misses_below_threshold() -> None:
    cache = SemanticCache()
    wid = uuid.uuid4()
    cache.store(wid, [1.0, 0.0, 0.0], CachedAnswer("cached", []))

    assert cache.lookup(wid, [0.0, 1.0, 0.0], threshold=0.9) is None


def test_cache_is_workspace_isolated() -> None:
    cache = SemanticCache()
    a, b = uuid.uuid4(), uuid.uuid4()
    cache.store(a, [1.0, 0.0], CachedAnswer("a", []))

    assert cache.lookup(b, [1.0, 0.0], threshold=0.9) is None


def test_store_evicts_oldest_when_full() -> None:
    cache = SemanticCache(max_entries=1)
    wid = uuid.uuid4()
    cache.store(wid, [1.0, 0.0], CachedAnswer("old", []))
    cache.store(wid, [0.0, 1.0], CachedAnswer("new", []))

    assert cache.lookup(wid, [1.0, 0.0], threshold=0.99) is None
    assert cache.lookup(wid, [0.0, 1.0], threshold=0.99).answer == "new"


async def _workspace(client: AsyncClient, email: str) -> dict[str, object]:
    await client.post(
        f"{_AUTH}/register", json={"email": email, "password": _PASSWORD}
    )
    login = await client.post(
        f"{_AUTH}/login", json={"email": email, "password": _PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    ws = await client.post(_WS, json={"name": "KB"}, headers=headers)
    return {"workspace_id": ws.json()["id"], "headers": headers}


async def _chat(client, ws, conv_id, message: str) -> dict:
    resp = await client.post(
        f"{_WS}/{ws['workspace_id']}/conversations/{conv_id}/messages",
        json={"message": message},
        headers=ws["headers"],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["answer"]


async def _start(client, ws) -> str:
    created = await client.post(
        f"{_WS}/{ws['workspace_id']}/conversations",
        json={"title": "Q&A"},
        headers=ws["headers"],
    )
    return created.json()["id"]


async def test_chat_populates_cache(client: AsyncClient) -> None:
    ws = await _workspace(client, "cache-fill@example.com")
    files = {"file": ("kb.txt", b"Nexus was founded in 2021.", "text/plain")}
    await client.post(
        f"{_WS}/{ws['workspace_id']}/documents", files=files, headers=ws["headers"]
    )
    conv_id = await _start(client, ws)

    await _chat(client, ws, conv_id, "When was Nexus founded?")

    wid = uuid.UUID(ws["workspace_id"])
    (vec,) = await get_embedding_provider().embed(["When was Nexus founded?"])
    assert get_semantic_cache().lookup(wid, vec, threshold=0.95) is not None


async def test_cache_hit_short_circuits_llm(client: AsyncClient) -> None:
    ws = await _workspace(client, "cache-hit@example.com")
    conv_id = await _start(client, ws)  # empty KB -> would normally fall back

    question = "What is the secret handshake?"
    wid = uuid.UUID(ws["workspace_id"])
    (vec,) = await get_embedding_provider().embed([question])
    get_semantic_cache().store(
        wid, vec, CachedAnswer("SEEDED cached answer [1]", [])
    )

    answer = await _chat(client, ws, conv_id, question)
    assert answer["content"] == "SEEDED cached answer [1]"
