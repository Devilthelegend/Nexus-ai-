"""Hybrid retrieval for RAG: dense + keyword, fused, reranked and budgeted.

Dense recall comes from the vector store; keyword recall from a lexical scan of
workspace chunks. The two ranked lists are merged with reciprocal-rank fusion,
reranked by lexical overlap, then packed into a token budget with citations.
All access is workspace-scoped for tenant isolation.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.vectorstore.base import VectorStore
from app.core.config import Settings, get_settings
from app.models.chunk import Chunk
from app.models.document import Document

_WORD_RE = re.compile(r"[a-z0-9]+")
_RRF_K = 60


@dataclass(slots=True)
class RetrievedChunk:
    """A candidate chunk with its fused/rerank score."""

    chunk_id: str
    document_id: str
    text: str
    ordinal: int | None
    page: int | None
    section: str | None
    score: float


@dataclass(slots=True)
class RetrievalResult:
    """Assembled context string plus the citations that back it."""

    context: str
    citations: list[dict[str, object]]


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


async def _dense(
    embedder: EmbeddingProvider,
    store: VectorStore,
    workspace_id: uuid.UUID,
    query: str,
    limit: int,
) -> list[RetrievedChunk]:
    (vector,) = await embedder.embed([query])
    await store.ensure_ready(embedder.dimension)
    hits = await store.search(vector, workspace_id=workspace_id, limit=limit)
    return [
        RetrievedChunk(
            chunk_id=hit.payload.get("chunk_id", hit.id),
            document_id=str(hit.payload.get("document_id", "")),
            text=str(hit.payload.get("text", "")),
            ordinal=hit.payload.get("ordinal"),
            page=hit.payload.get("page"),
            section=hit.payload.get("section"),
            score=hit.score,
        )
        for hit in hits
    ]


async def _keyword(
    db: AsyncSession, workspace_id: uuid.UUID, query: str, limit: int
) -> list[RetrievedChunk]:
    terms = set(_tokens(query))
    if not terms:
        return []
    conditions = [Chunk.text.ilike(f"%{term}%") for term in terms]
    result = await db.execute(
        select(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
            or_(*conditions),
        )
        .limit(limit * 4)
    )
    scored: list[RetrievedChunk] = []
    for chunk in result.scalars().all():
        overlap = len(terms & set(_tokens(chunk.text)))
        if overlap:
            scored.append(
                RetrievedChunk(
                    chunk_id=str(chunk.id),
                    document_id=str(chunk.document_id),
                    text=chunk.text,
                    ordinal=chunk.ordinal,
                    page=chunk.page,
                    section=chunk.section,
                    score=float(overlap),
                )
            )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]


def _fuse(*ranked: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    fused: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    for chunks in ranked:
        for rank, chunk in enumerate(chunks):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            fused.setdefault(chunk.chunk_id, chunk)
    ordered = sorted(fused.values(), key=lambda c: scores[c.chunk_id], reverse=True)
    for chunk in ordered:
        chunk.score = scores[chunk.chunk_id]
    return ordered


def _rerank(query: str, candidates: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    terms = set(_tokens(query))
    ranked = sorted(
        candidates,
        key=lambda c: (len(terms & set(_tokens(c.text))), c.score),
        reverse=True,
    )
    return ranked[:top_k]


def _assemble(chunks: list[RetrievedChunk], budget: int) -> RetrievalResult:
    lines: list[str] = []
    citations: list[dict[str, object]] = []
    used = 0
    for index, chunk in enumerate(chunks, start=1):
        cost = len(_tokens(chunk.text))
        if lines and used + cost > budget:
            break
        used += cost
        lines.append(f"[{index}] {chunk.text}")
        citations.append(
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "ordinal": chunk.ordinal,
                "page": chunk.page,
                "section": chunk.section,
                "score": round(chunk.score, 6),
                "text": chunk.text,
            }
        )
    return RetrievalResult(context="\n".join(lines), citations=citations)


async def retrieve(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    query: str,
    embedder: EmbeddingProvider,
    store: VectorStore,
    settings: Settings | None = None,
) -> RetrievalResult:
    """Run hybrid retrieval and return budgeted context with citations."""
    settings = settings or get_settings()
    dense = await _dense(embedder, store, workspace_id, query, settings.retrieval_top_k)
    keyword = await _keyword(db, workspace_id, query, settings.retrieval_top_k)
    fused = _fuse(dense, keyword)
    top = _rerank(query, fused, settings.rerank_top_k)
    return _assemble(top, settings.context_token_budget)
