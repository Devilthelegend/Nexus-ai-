"""Agent memory: short-term conversation recall and long-term summaries.

Short-term memory is the recent turns of the current conversation, read straight
from the message log so the agent has continuity within a thread. Long-term
memory is a workspace-scoped, vector-backed store of prior run summaries; the
most similar summaries to the current objective are recalled so the agent can
build on earlier conclusions across conversations. Both are injected into the
prompt as read-only context and never cited. The long-term store is an in-process
singleton mirroring the semantic cache; a distributed backend can implement the
same surface later.
"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.message import Message


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


async def recent_turns(
    db: AsyncSession, conversation_id: uuid.UUID, limit: int
) -> list[tuple[str, str]]:
    """Return the last ``limit`` (role, content) turns in chronological order."""
    if limit <= 0:
        return []
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return [(m.role.value, m.content) for m in messages]


@dataclass(slots=True)
class _Entry:
    vector: list[float]
    summary: str


@dataclass(slots=True)
class AgentMemory:
    """In-process nearest-neighbour store of run summaries, per workspace."""

    max_entries: int = 256
    _by_workspace: dict[uuid.UUID, list[_Entry]] = field(default_factory=dict)

    def recall(
        self, workspace_id: uuid.UUID, query_vector: Sequence[float], top_k: int
    ) -> list[str]:
        """Return the ``top_k`` most similar summaries for the workspace."""
        entries = self._by_workspace.get(workspace_id)
        if not entries or top_k <= 0:
            return []
        scored = sorted(
            entries,
            key=lambda e: _cosine(query_vector, e.vector),
            reverse=True,
        )
        return [entry.summary for entry in scored[:top_k]]

    def remember(
        self,
        workspace_id: uuid.UUID,
        query_vector: Sequence[float],
        summary: str,
    ) -> None:
        """Store a run summary, evicting the oldest when the workspace is full."""
        entries = self._by_workspace.setdefault(workspace_id, [])
        entries.append(_Entry(vector=list(query_vector), summary=summary))
        if len(entries) > self.max_entries:
            del entries[0]

    def clear(self) -> None:
        """Drop all remembered summaries (used in tests)."""
        self._by_workspace.clear()


@lru_cache(maxsize=1)
def get_agent_memory() -> AgentMemory:
    """Return the process-wide agent long-term memory singleton."""
    return AgentMemory(max_entries=get_settings().agent_long_term_max_entries)


def format_memory_block(
    short_term: list[tuple[str, str]], long_term: list[str]
) -> str:
    """Render recalled memory as a read-only prompt section (or empty)."""
    parts: list[str] = []
    if long_term:
        recalled = "\n".join(f"- {summary}" for summary in long_term)
        parts.append(f"Relevant past conclusions:\n{recalled}")
    if short_term:
        turns = "\n".join(f"{role}: {content}" for role, content in short_term)
        parts.append(f"Recent conversation:\n{turns}")
    if not parts:
        return ""
    body = "\n\n".join(parts)
    return f"Conversation memory (for context only, do not cite):\n{body}\n\n"
