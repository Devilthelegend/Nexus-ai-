"""Tests for the RAG chat pipeline, conversations and retrieval fusion."""

import json

import pytest
from httpx import AsyncClient

from app.ai.vectorstore.factory import _memory_store
from app.services.retrieval import RetrievedChunk, _fuse, _rerank

_AUTH = "/api/v1/auth"
_WS = "/api/v1/workspaces"
_PASSWORD = "s3cret-password"


@pytest.fixture(autouse=True)
def isolate_rag(tmp_path, monkeypatch):
    """Point uploads at a temp dir and reset the in-memory vector store."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    _memory_store.cache_clear()
    yield
    _memory_store.cache_clear()


async def _workspace(client: AsyncClient, email: str) -> dict[str, object]:
    await client.post(f"{_AUTH}/register", json={"email": email, "password": _PASSWORD})
    login = await client.post(f"{_AUTH}/login", json={"email": email, "password": _PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    ws = await client.post(_WS, json={"name": "KB"}, headers=headers)
    return {"workspace_id": ws.json()["id"], "headers": headers}


async def _upload(client, ws, text: bytes, name: str = "kb.txt") -> None:
    files = {"file": (name, text, "text/plain")}
    resp = await client.post(
        f"{_WS}/{ws['workspace_id']}/documents", files=files, headers=ws["headers"]
    )
    assert resp.json()["status"] == "indexed", resp.text


def _conv_url(ws) -> str:
    return f"{_WS}/{ws['workspace_id']}/conversations"


async def _start(client, ws) -> str:
    created = await client.post(_conv_url(ws), json={"title": "Q&A"}, headers=ws["headers"])
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_chat_returns_grounded_answer_with_citations(client: AsyncClient) -> None:
    ws = await _workspace(client, "rag-owner@example.com")
    await _upload(client, ws, b"The capital of Nexus is Aurora, a coastal city.")
    conv_id = await _start(client, ws)

    resp = await client.post(
        f"{_conv_url(ws)}/{conv_id}/messages",
        json={"message": "What is the capital of Nexus?"},
        headers=ws["headers"],
    )
    assert resp.status_code == 200, resp.text
    answer = resp.json()["answer"]
    assert answer["role"] == "assistant"
    assert "[1]" in answer["content"]
    assert answer["citations"], "expected at least one citation"
    assert "Aurora" in answer["citations"][0]["text"]


async def test_chat_stream_emits_tokens_and_done(client: AsyncClient) -> None:
    ws = await _workspace(client, "stream@example.com")
    await _upload(client, ws, b"The capital of Nexus is Aurora, a coastal city.")
    conv_id = await _start(client, ws)

    resp = await client.post(
        f"{_conv_url(ws)}/{conv_id}/messages/stream",
        json={"message": "What is the capital of Nexus?"},
        headers=ws["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = resp.text
    assert "event: token" in body
    assert "event: done" in body

    done_line = next(
        line[len("data: ") :]
        for line in body.splitlines()
        if line.startswith("data: ") and '"type": "done"' in line
    )
    done = json.loads(done_line)
    assert done["message_id"]
    assert done["citations"], "expected citations on the final event"

    # The streamed assistant turn is persisted just like the blocking route.
    history = await client.get(f"{_conv_url(ws)}/{conv_id}/messages", headers=ws["headers"])
    roles = [m["role"] for m in history.json()]
    assert roles == ["user", "assistant"]


async def test_chat_without_knowledge_returns_fallback(client: AsyncClient) -> None:
    ws = await _workspace(client, "empty-kb@example.com")
    conv_id = await _start(client, ws)

    resp = await client.post(
        f"{_conv_url(ws)}/{conv_id}/messages",
        json={"message": "Anything here?"},
        headers=ws["headers"],
    )
    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert "couldn't find" in answer["content"].lower()
    assert not answer["citations"]


async def test_messages_are_persisted_in_order(client: AsyncClient) -> None:
    ws = await _workspace(client, "persist@example.com")
    await _upload(client, ws, b"Nexus ships weekly product updates.")
    conv_id = await _start(client, ws)

    await client.post(
        f"{_conv_url(ws)}/{conv_id}/messages",
        json={"message": "How often does Nexus ship updates?"},
        headers=ws["headers"],
    )
    history = await client.get(f"{_conv_url(ws)}/{conv_id}/messages", headers=ws["headers"])
    roles = [m["role"] for m in history.json()]
    assert roles == ["user", "assistant"]


async def test_conversation_tenant_isolation(client: AsyncClient) -> None:
    owner = await _workspace(client, "conv-owner@example.com")
    outsider = await _workspace(client, "conv-outsider@example.com")
    conv_id = await _start(client, owner)

    hidden = await client.get(f"{_conv_url(owner)}/{conv_id}", headers=outsider["headers"])
    assert hidden.status_code == 404

    blocked = await client.post(
        f"{_conv_url(owner)}/{conv_id}/messages",
        json={"message": "leak?"},
        headers=outsider["headers"],
    )
    assert blocked.status_code == 404


async def test_create_conversation_requires_membership(client: AsyncClient) -> None:
    owner = await _workspace(client, "cm-owner@example.com")
    outsider = await _workspace(client, "cm-outsider@example.com")

    resp = await client.post(
        _conv_url(owner), json={"title": "sneaky"}, headers=outsider["headers"]
    )
    assert resp.status_code == 404


def test_reciprocal_rank_fusion_and_rerank() -> None:
    def chunk(cid: str, text: str) -> RetrievedChunk:
        return RetrievedChunk(cid, "doc", text, 0, None, None, 0.0)

    dense = [chunk("a", "alpha beta"), chunk("b", "gamma")]
    keyword = [chunk("b", "gamma"), chunk("c", "alpha delta")]

    fused = _fuse(dense, keyword)
    assert fused[0].chunk_id == "b"  # appears in both lists

    reranked = _rerank("alpha", fused, top_k=2)
    assert reranked[0].chunk_id in {"a", "c"}  # lexical overlap wins
    assert len(reranked) == 2
