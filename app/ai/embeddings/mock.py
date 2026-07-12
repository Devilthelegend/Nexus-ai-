"""Deterministic, offline mock embedding provider.

Uses a hashing bag-of-words projection so that texts sharing vocabulary produce
similar vectors. This makes semantic-search behaviour meaningful in tests and
local development without any API key or network access.
"""

import hashlib
import math
import re
from collections.abc import Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class MockEmbeddingProvider:
    """Hashing-based embeddings; stable across processes and runs."""

    def __init__(self, model: str, dimension: int) -> None:
        self._model = model
        self._dimension = dimension

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]
