"""Pure retrieval metrics.

Each metric takes an ordered list of retrieved item ids (best first) and the set
of ids that are relevant for the query. They are deliberately free of any I/O so
they can be unit-tested in isolation and reused by the offline runner.
"""

from collections.abc import Sequence


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant ids that appear in the top-``k`` retrieved ids."""
    if not relevant:
        return 0.0
    top = set(retrieved[:k])
    return len(top & relevant) / len(relevant)


def precision_at_k(
    retrieved: Sequence[str], relevant: set[str], k: int
) -> float:
    """Fraction of the top-``k`` retrieved ids that are relevant."""
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in relevant)
    return hits / len(top)


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    """Reciprocal of the rank of the first relevant id (0.0 if none)."""
    for index, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean, returning 0.0 for an empty sequence."""
    return sum(values) / len(values) if values else 0.0
