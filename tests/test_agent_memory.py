"""Tests for agent memory: long-term recall store and short-term turns."""

import uuid

import pytest
from httpx import AsyncClient

from app.ai.embeddings.factory import get_embedding_provider
from app.ai.vectorstore.factory import _memory_store
from app.services.agent.memory import (
    AgentMemory,
    format_memory_block,
    get_agent_memory,
)

_AUTH = "/api/v1/auth"
_WS = "/api/v1/workspaces"
_PASSWORD = "s3cret-password"


@pytest.fixture(autouse=True)
def isolate_memory(tmp_path, monkeypatch):
    """Temp uploads, clean vector store and clean agent memory per test."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    _memory_store.cache_clear()
    get_agent_memory().clear()
    yield
    _memory_store.cache_clear()
    get_agent_memory().clear()


def test_recall_returns_most_similar_summary() -> None:
    mem = AgentMemory()
    wid = uuid.uuid4()
    mem.remember(wid, [1.0, 0.0, 0.0], "capital summary")
    mem.remember(wid, [0.0, 1.0, 0.0], "founding summary")

    assert mem.recall(wid, [1.0, 0.0, 0.0], top_k=1) == ["capital summary"]


def test_recall_is_workspace_isolated() -> None:
    mem = AgentMemory()
    a, b = uuid.uuid4(), uuid.uuid4()
    mem.remember(a, [1.0, 0.0], "a-only")

    assert mem.recall(b, [1.0, 0.0], top_k=3) == []


def test_remember_evicts_oldest_when_full() -> None:
    mem = AgentMemory(max_entries=1)
    wid = uuid.uuid4()
    mem.remember(wid, [1.0, 0.0], "old")
    mem.remember(wid, [0.0, 1.0], "new")

    assert mem.recall(wid, [1.0, 0.0], top_k=5) == ["new"]


def test_format_memory_block_empty_and_populated() -> None:
    assert format_memory_block([], []) == ""
    block = format_memory_block([("user", "hi")], ["prior conclusion"])
    assert "do not cite" in block
    assert "prior conclusion" in block
    assert "user: hi" in block


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


async def test_agent_run_remembers_summary(client: AsyncClient) -> None:
    ws = await _workspace(client, "mem-owner@example.com")
    files = {"file": ("kb.txt", b"The capital of Nexus is Aurora.", "text/plain")}
    await client.post(
        f"{_WS}/{ws['workspace_id']}/documents", files=files, headers=ws["headers"]
    )
    created = await client.post(
        f"{_WS}/{ws['workspace_id']}/conversations",
        json={"title": "Agent"},
        headers=ws["headers"],
    )
    conv_id = created.json()["id"]

    objective = "What is the capital of Nexus?"
    resp = await client.post(
        f"{_WS}/{ws['workspace_id']}/conversations/{conv_id}/agent/runs",
        json={"objective": objective},
        headers=ws["headers"],
    )
    assert resp.status_code == 201, resp.text

    wid = uuid.UUID(ws["workspace_id"])
    (vec,) = await get_embedding_provider().embed([objective])
    recalled = get_agent_memory().recall(wid, vec, top_k=1)
    assert recalled and "Aurora" in recalled[0]
