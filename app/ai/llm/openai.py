"""OpenAI-compatible chat completion provider.

Works with the OpenAI API and any OpenAI-compatible ``/chat/completions``
endpoint (e.g. Groq, OpenRouter, or a local server) by pointing ``base_url`` at
the target. Enabled only when ``LLM_PROVIDER=openai`` and an API key is
configured; the deterministic mock provider remains the default for tests and
offline runs.
"""

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from app.ai.llm.base import LLMMessage, LLMResult

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class OpenAILLMProvider:
    """Chat completions via an OpenAI-compatible ``/chat/completions`` API."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI provider requires an API key (set LLM_API_KEY).")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    @property
    def _url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, messages: Sequence[LLMMessage], *, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature,
            "stream": stream,
        }
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens
        return payload

    async def complete(self, messages: Sequence[LLMMessage]) -> LLMResult:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                self._url,
                headers=self._headers(),
                json=self._payload(messages, stream=False),
            )
            resp.raise_for_status()
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )

    async def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        async with (
            httpx.AsyncClient(timeout=_TIMEOUT) as client,
            client.stream(
                "POST",
                self._url,
                headers=self._headers(),
                json=self._payload(messages, stream=True),
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                piece = _parse_sse_delta(line)
                if piece:
                    yield piece


def _parse_sse_delta(line: str) -> str | None:
    """Extract the incremental content from one SSE ``data:`` line.

    Returns ``None`` for keep-alives, the ``[DONE]`` sentinel, and any line
    without a text delta.
    """
    if not line or not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = chunk.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if content else None
