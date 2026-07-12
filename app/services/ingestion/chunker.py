"""Split extracted pages into overlapping chunks with structural metadata."""

import re
from dataclasses import dataclass

from app.services.ingestion.extractors import ExtractedPage

_WORD_RE = re.compile(r"\S+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)


@dataclass(slots=True)
class TextChunk:
    """A prepared chunk ready for embedding."""

    ordinal: int
    text: str
    token_count: int
    page: int | None = None
    section: str | None = None


def _estimate_tokens(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _latest_section(text: str) -> str | None:
    matches = _HEADING_RE.findall(text)
    return matches[-1].strip() if matches else None


def chunk_pages(pages: list[ExtractedPage], size: int, overlap: int) -> list[TextChunk]:
    """Produce overlapping character windows per page, preserving metadata.

    ``size`` and ``overlap`` are character counts; ``overlap`` is clamped to be
    strictly smaller than ``size`` to guarantee forward progress.
    """
    if size <= 0:
        raise ValueError("chunk size must be positive")
    step = max(1, size - max(0, min(overlap, size - 1)))

    chunks: list[TextChunk] = []
    ordinal = 0
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        section = _latest_section(text)
        start = 0
        while start < len(text):
            window = text[start : start + size].strip()
            if window:
                chunks.append(
                    TextChunk(
                        ordinal=ordinal,
                        text=window,
                        token_count=_estimate_tokens(window),
                        page=page.page,
                        section=section,
                    )
                )
                ordinal += 1
            start += step
    return chunks
