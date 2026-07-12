"""Deterministic, offline mock LLM provider.

Grounds its answer strictly in the retrieved context passed via the system
message so that RAG behaviour (citations, "no answer" fallback) is meaningful in
tests and local development without any API key or network access.
"""

import re
from collections.abc import AsyncIterator, Sequence

from app.ai.llm.base import LLMMessage, LLMResult

_NO_CONTEXT = "(none)"
_FALLBACK = (
    "I couldn't find relevant information in the knowledge base to answer that."
)
_WORD_RE = re.compile(r"\S+")


def _count(text: str) -> int:
    return len(_WORD_RE.findall(text))


class MockLLMProvider:
    """Rule-based, context-grounded chat completion."""

    def __init__(self, model: str) -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def _answer(self, messages: Sequence[LLMMessage]) -> str:
        system = next(
            (m.content for m in messages if m.role == "system"), ""
        )
        question = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        has_context = "[1]" in system and _NO_CONTEXT not in system
        if not has_context:
            return _FALLBACK

        # Echo the first cited passage to demonstrate grounding.
        match = re.search(r"\[1\]\s*(.+)", system)
        snippet = (match.group(1).strip() if match else "")[:280]
        return (
            f'Based on the knowledge base, regarding "{question.strip()}": '
            f"{snippet} [1]"
        )

    async def complete(self, messages: Sequence[LLMMessage]) -> LLMResult:
        text = self._answer(messages)
        prompt_tokens = sum(_count(m.content) for m in messages)
        return LLMResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=_count(text),
        )

    async def stream(
        self, messages: Sequence[LLMMessage]
    ) -> AsyncIterator[str]:
        text = self._answer(messages)
        for token in text.split(" "):
            yield token + " "
