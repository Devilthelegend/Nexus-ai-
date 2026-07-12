"""RAG chat orchestration: retrieve -> prompt -> LLM -> persist.

Persists both the user turn and the grounded assistant turn (with citations and
token usage) so a conversation is a durable, auditable record.
"""

import re
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.llm.base import LLMMessage, LLMProvider
from app.ai.vectorstore.base import VectorStore
from app.core.config import Settings, get_settings
from app.core.observability import record_llm_usage
from app.models.conversation import Conversation
from app.models.enums import MessageRole
from app.models.message import Message
from app.services import retrieval
from app.services.semantic_cache import CachedAnswer, get_semantic_cache

_WORD_RE = re.compile(r"\S+")

_SYSTEM_TEMPLATE = (
    "You are NexusAI, a helpful assistant. Answer the user's question using "
    "ONLY the context below. Cite sources inline as [n]. If the context does "
    "not contain the answer, say you don't have enough information.\n\n"
    "Context:\n{context}"
)


def _count(text: str) -> int:
    return len(_WORD_RE.findall(text))


async def generate_answer(
    db: AsyncSession,
    *,
    conversation: Conversation,
    message: str,
    embedder: EmbeddingProvider,
    store: VectorStore,
    llm: LLMProvider,
    settings: Settings | None = None,
) -> Message:
    """Persist the user turn, run RAG, and persist the assistant turn."""
    settings = settings or get_settings()
    conversation_id = conversation.id
    workspace_id = conversation.workspace_id

    db.add(
        Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=message,
            tokens=_count(message),
        )
    )
    await db.flush()

    cache = get_semantic_cache() if settings.semantic_cache_enabled else None
    query_vector: list[float] | None = None
    if cache is not None:
        (query_vector,) = await embedder.embed([message])
        hit = cache.lookup(workspace_id, query_vector, settings.semantic_cache_threshold)
        if hit is not None:
            return await _persist_assistant(db, conversation_id, hit.answer, hit.citations)

    result = await retrieval.retrieve(
        db,
        workspace_id=workspace_id,
        query=message,
        embedder=embedder,
        store=store,
        settings=settings,
    )
    system = _SYSTEM_TEMPLATE.format(context=result.context or "(none)")
    completion = await llm.complete([LLMMessage("system", system), LLMMessage("user", message)])
    record_llm_usage(
        completion.total_tokens,
        completion.total_tokens / 1000 * settings.llm_cost_per_1k_tokens,
    )

    if cache is not None and query_vector is not None:
        cache.store(
            workspace_id,
            query_vector,
            CachedAnswer(answer=completion.text, citations=result.citations),
        )

    return await _persist_assistant(db, conversation_id, completion.text, result.citations)


async def _persist_assistant(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    content: str,
    citations: list[dict[str, object]],
) -> Message:
    """Persist and return a grounded assistant turn."""
    assistant = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=content,
        tokens=_count(content),
        citations=citations or None,
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return assistant


async def stream_answer(
    db: AsyncSession,
    *,
    conversation: Conversation,
    message: str,
    embedder: EmbeddingProvider,
    store: VectorStore,
    llm: LLMProvider,
    settings: Settings | None = None,
) -> AsyncIterator[dict[str, object]]:
    """Same pipeline as :func:`generate_answer`, streaming token deltas.

    Yields ``{"type": "token", "text": ...}`` events as the answer is produced
    and a final ``{"type": "done", ...}`` event once the assistant turn has been
    persisted with its citations.
    """
    settings = settings or get_settings()
    conversation_id = conversation.id
    workspace_id = conversation.workspace_id

    db.add(
        Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=message,
            tokens=_count(message),
        )
    )
    await db.flush()

    result = await retrieval.retrieve(
        db,
        workspace_id=workspace_id,
        query=message,
        embedder=embedder,
        store=store,
        settings=settings,
    )
    system = _SYSTEM_TEMPLATE.format(context=result.context or "(none)")

    parts: list[str] = []
    async for delta in llm.stream([LLMMessage("system", system), LLMMessage("user", message)]):
        parts.append(delta)
        yield {"type": "token", "text": delta}

    text = "".join(parts)
    stream_tokens = _count(system) + _count(message) + _count(text)
    record_llm_usage(
        stream_tokens,
        stream_tokens / 1000 * settings.llm_cost_per_1k_tokens,
    )
    assistant = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=text,
        tokens=_count(text),
        citations=result.citations or None,
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)

    yield {
        "type": "done",
        "message_id": str(assistant.id),
        "citations": result.citations or [],
    }
