"""Tests for the agent orchestrator, AgentRun records and its API."""

import pytest
from httpx import AsyncClient

from app.ai.vectorstore.factory import _memory_store

_AUTH = "/api/v1/auth"
_WS = "/api/v1/workspaces"
_PASSWORD = "s3cret-password"


@pytest.fixture(autouse=True)
def isolate_agent(tmp_path, monkeypatch):
    """Point uploads at a temp dir and reset the in-memory vector store."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    _memory_store.cache_clear()
    yield
    _memory_store.cache_clear()


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


async def _upload(client, ws, text: bytes, name: str = "kb.txt") -> None:
    files = {"file": (name, text, "text/plain")}
    resp = await client.post(
        f"{_WS}/{ws['workspace_id']}/documents", files=files, headers=ws["headers"]
    )
    assert resp.json()["status"] == "indexed", resp.text


def _conv_url(ws) -> str:
    return f"{_WS}/{ws['workspace_id']}/conversations"


async def _start(client, ws) -> str:
    created = await client.post(
        _conv_url(ws), json={"title": "Agent"}, headers=ws["headers"]
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _agent_url(ws, conv_id: str) -> str:
    return f"{_conv_url(ws)}/{conv_id}/agent/runs"


async def test_agent_run_grounded_records_steps_and_tool_calls(
    client: AsyncClient,
) -> None:
    ws = await _workspace(client, "agent-owner@example.com")
    await _upload(client, ws, b"The capital of Nexus is Aurora, a coastal city.")
    conv_id = await _start(client, ws)

    resp = await client.post(
        _agent_url(ws, conv_id),
        json={"objective": "What is the capital of Nexus?"},
        headers=ws["headers"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    run = body["run"]
    assert run["status"] == "completed"
    assert len(run["steps"]) == 2
    assert run["tool_calls"][0]["tool"] == "knowledge_base_search"
    assert run["tool_calls"][0]["result_count"] >= 1
    assert run["cost_usd"] == 0.0
    assert run["latency_ms"] >= 0
    assert run["answer_message_id"]

    answer = body["answer"]
    assert answer["role"] == "assistant"
    assert "[1]" in answer["content"]
    assert "Aurora" in answer["citations"][0]["text"]


async def test_agent_run_persists_conversation_turns(client: AsyncClient) -> None:
    ws = await _workspace(client, "agent-persist@example.com")
    await _upload(client, ws, b"Nexus ships weekly product updates.")
    conv_id = await _start(client, ws)

    await client.post(
        _agent_url(ws, conv_id),
        json={"objective": "How often does Nexus ship updates?"},
        headers=ws["headers"],
    )
    history = await client.get(
        f"{_conv_url(ws)}/{conv_id}/messages", headers=ws["headers"]
    )
    roles = [m["role"] for m in history.json()]
    assert roles == ["user", "assistant"]


async def test_agent_run_empty_kb_still_completes(client: AsyncClient) -> None:
    ws = await _workspace(client, "agent-empty@example.com")
    conv_id = await _start(client, ws)

    resp = await client.post(
        _agent_url(ws, conv_id),
        json={"objective": "Anything here?"},
        headers=ws["headers"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["run"]["status"] == "completed"
    assert body["run"]["tool_calls"][0]["result_count"] == 0
    assert "couldn't find" in body["answer"]["content"].lower()
    assert not body["answer"]["citations"]


async def test_agent_list_and_get_runs(client: AsyncClient) -> None:
    ws = await _workspace(client, "agent-list@example.com")
    await _upload(client, ws, b"Nexus was founded in 2021.")
    conv_id = await _start(client, ws)

    first = await client.post(
        _agent_url(ws, conv_id),
        json={"objective": "When was Nexus founded?"},
        headers=ws["headers"],
    )
    run_id = first.json()["run"]["id"]

    listed = await client.get(_agent_url(ws, conv_id), headers=ws["headers"])
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [run_id]

    fetched = await client.get(
        f"{_agent_url(ws, conv_id)}/{run_id}", headers=ws["headers"]
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == run_id

    missing = await client.get(
        f"{_agent_url(ws, conv_id)}/{conv_id}", headers=ws["headers"]
    )
    assert missing.status_code == 404


async def test_agent_run_tenant_isolation(client: AsyncClient) -> None:
    owner = await _workspace(client, "agent-iso-owner@example.com")
    outsider = await _workspace(client, "agent-iso-out@example.com")
    conv_id = await _start(client, owner)

    blocked = await client.post(
        _agent_url(owner, conv_id),
        json={"objective": "leak?"},
        headers=outsider["headers"],
    )
    assert blocked.status_code == 404

    hidden = await client.get(
        _agent_url(owner, conv_id), headers=outsider["headers"]
    )
    assert hidden.status_code == 404
