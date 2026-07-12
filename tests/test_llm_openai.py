"""Tests for the OpenAI-compatible LLM provider (no network access).

An ``httpx.MockTransport`` stands in for the real ``/chat/completions`` API so
the request shape, token accounting and streaming delta parsing are exercised
deterministically.
"""

import json

import httpx
import pytest

from app.ai.llm import openai as openai_mod
from app.ai.llm.base import LLMMessage
from app.ai.llm.openai import OpenAILLMProvider, _parse_sse_delta

_MESSAGES = [
    LLMMessage("system", "Context: [1] Aurora is the capital."),
    LLMMessage("user", "What is the capital?"),
]


def _install_transport(monkeypatch, handler):
    """Route the provider's AsyncClient through a MockTransport handler."""
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(openai_mod.httpx, "AsyncClient", factory)


def test_requires_api_key() -> None:
    with pytest.raises(ValueError):
        OpenAILLMProvider(model="gpt-x", api_key="")


async def test_complete_parses_text_and_usage(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Aurora is the capital [1]"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            },
        )

    _install_transport(monkeypatch, handler)
    provider = OpenAILLMProvider(
        model="gpt-test", api_key="secret-key", max_tokens=256
    )
    result = await provider.complete(_MESSAGES)

    assert result.text == "Aurora is the capital [1]"
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 4
    assert result.total_tokens == 15
    assert seen["auth"] == "Bearer secret-key"
    body = seen["body"]
    assert body["model"] == "gpt-test"
    assert body["stream"] is False
    assert body["max_tokens"] == 256
    assert body["messages"][0]["role"] == "system"


async def test_stream_yields_content_deltas(monkeypatch) -> None:
    sse = (
        'data: {"choices":[{"delta":{"content":"Aurora"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" is"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" the capital"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=sse.encode())

    _install_transport(monkeypatch, handler)
    provider = OpenAILLMProvider(model="gpt-test", api_key="secret-key")

    deltas = [chunk async for chunk in provider.stream(_MESSAGES)]
    assert deltas == ["Aurora", " is", " the capital"]
    assert "".join(deltas) == "Aurora is the capital"


async def test_complete_raises_on_http_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    _install_transport(monkeypatch, handler)
    provider = OpenAILLMProvider(model="gpt-test", api_key="bad-key")

    with pytest.raises(httpx.HTTPStatusError):
        await provider.complete(_MESSAGES)


def test_parse_sse_delta_ignores_noise() -> None:
    assert _parse_sse_delta("") is None
    assert _parse_sse_delta(": keep-alive") is None
    assert _parse_sse_delta("data: [DONE]") is None
    assert _parse_sse_delta("data: {not json}") is None
    assert _parse_sse_delta('data: {"choices":[]}') is None
    assert (
        _parse_sse_delta('data: {"choices":[{"delta":{"content":"hi"}}]}') == "hi"
    )
