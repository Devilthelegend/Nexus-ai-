"""Workspace-scoped semantic cache for RAG answers.

Caches grounded answers keyed by the query embedding so that a semantically
similar follow-up question can reuse a prior answer (and its citations) without
another retrieval + LLM round-trip. Entries are isolated per workspace for
tenant safety and bounded per workspace to cap memory. The default backend is
an in-process singleton; a distributed cache (e.g. Redis) can implement the
same small surface later.
"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import get_settings


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass(slots=True)
class CachedAnswer:
    """A previously produced answer and the citations that backed it."""

    answer: str
    citations: list[dict[str, object]]


@dataclass(slots=True)
class _Entry:
    vector: list[float]
    value: CachedAnswer


@dataclass(slots=True)
class SemanticCache:
    """In-process nearest-neighbour cache of answers, scoped by workspace."""

    max_entries: int = 512
    _by_workspace: dict[uuid.UUID, list[_Entry]] = field(default_factory=dict)

    def lookup(
        self,
        workspace_id: uuid.UUID,
        query_vector: Sequence[float],
        threshold: float,
    ) -> CachedAnswer | None:
        """Return the best entry above ``threshold`` for the workspace."""
        entries = self._by_workspace.get(workspace_id)
        if not entries:
            return None
        best: CachedAnswer | None = None
        best_score = threshold
        for entry in entries:
            score = _cosine(query_vector, entry.vector)
            if score >= best_score:
                best_score = score
                best = entry.value
        return best

    def store(
        self,
        workspace_id: uuid.UUID,
        query_vector: Sequence[float],
        value: CachedAnswer,
    ) -> None:
        """Add an entry, evicting the oldest when the workspace is full."""
        entries = self._by_workspace.setdefault(workspace_id, [])
        entries.append(_Entry(vector=list(query_vector), value=value))
        if len(entries) > self.max_entries:
            del entries[0]

    def clear(self) -> None:
        """Drop all cached entries (used in tests)."""
        self._by_workspace.clear()


@lru_cache(maxsize=1)
def get_semantic_cache() -> SemanticCache:
    """Return the process-wide semantic cache singleton."""
    return SemanticCache(max_entries=get_settings().semantic_cache_max_entries)
