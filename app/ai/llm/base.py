"""LLM provider protocol and value types.

Keeps the RAG orchestration independent of any specific vendor (OpenAI, local
models, mock). Providers expose a blocking ``complete`` and a token-streaming
``stream`` over the same chat message list.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class LLMMessage:
    """A single chat message handed to the model (role + content)."""

    role: str
    content: str


@dataclass(slots=True)
class LLMResult:
    """A completion plus token usage for accounting."""

    text: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMProvider(Protocol):
    """A chat completion backend."""

    @property
    def model(self) -> str:
        """Identifier of the model (recorded for provenance)."""
        ...

    async def complete(self, messages: Sequence[LLMMessage]) -> LLMResult:
        """Return a full completion for the given chat messages."""
        ...

    def stream(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        """Yield the completion incrementally as text deltas."""
        ...
