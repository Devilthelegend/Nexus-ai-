"""Bounded agent orchestrator.

Drives a deterministic, bounded reasoning loop: search the knowledge base for
the objective, then synthesise a grounded answer with the LLM. Every reasoning
step and tool call is recorded, along with cost and latency, in an ``AgentRun``
so runs are fully auditable. Persists the objective and answer as conversation
turns, mirroring the RAG chat record.
"""

import re
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.llm.base import LLMMessage, LLMProvider
from app.ai.vectorstore.base import VectorStore
from app.core.config import Settings, get_settings
from app.core.observability import record_llm_usage
from app.models.agent_run import AgentRun
from app.models.conversation import Conversation
from app.models.enums import AgentRunStatus, MessageRole
from app.models.message import Message
from app.services.agent import memory
from app.services.agent.tools import KnowledgeBaseSearchTool, ToolContext

_WORD_RE = re.compile(r"\S+")

_SYSTEM_TEMPLATE = (
    "You are NexusAI, an autonomous research agent. Using ONLY the knowledge "
    "base passages below, answer the user's objective. Cite sources inline as "
    "[n]. If the passages do not contain the answer, say you don't have enough "
    "information.\n\n{memory}Knowledge base:\n{context}"
)

_TOOL = KnowledgeBaseSearchTool()


def _count(text: str) -> int:
    return len(_WORD_RE.findall(text))


async def run_agent(
    db: AsyncSession,
    *,
    conversation: Conversation,
    objective: str,
    embedder: EmbeddingProvider,
    store: VectorStore,
    llm: LLMProvider,
    settings: Settings | None = None,
) -> AgentRun:
    """Execute one bounded agent run and persist it as an ``AgentRun``."""
    settings = settings or get_settings()
    started = time.perf_counter()
    conversation_id = conversation.id
    context = ToolContext(db, conversation.workspace_id, embedder, store, settings)

    memory_block = ""
    memory_vector: list[float] | None = None
    if settings.agent_memory_enabled:
        short_term = await memory.recent_turns(db, conversation_id, settings.agent_short_term_turns)
        (memory_vector,) = await embedder.embed([objective])
        long_term = memory.get_agent_memory().recall(
            conversation.workspace_id,
            memory_vector,
            settings.agent_long_term_top_k,
        )
        memory_block = memory.format_memory_block(short_term, long_term)

    db.add(
        Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=objective,
            tokens=_count(objective),
        )
    )
    await db.flush()

    steps: list[dict[str, object]] = []
    tool_calls: list[dict[str, object]] = []
    citations: list[dict[str, object]] = []
    context_text = ""
    total_tokens = 0
    answer_text = ""
    status = AgentRunStatus.RUNNING
    error: str | None = None

    try:
        # Reserve the final step for answer synthesis; the rest is tool budget.
        if settings.agent_max_steps > 1:
            call_started = time.perf_counter()
            result = await _TOOL.run(context, objective)
            latency_ms = int((time.perf_counter() - call_started) * 1000)
            context_text = result.output
            citations = result.data
            tool_calls.append(
                {
                    "tool": _TOOL.name,
                    "input": objective,
                    "result_count": len(citations),
                    "latency_ms": latency_ms,
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "thought": "Search the knowledge base for the objective.",
                    "action": _TOOL.name,
                    "observation": f"Retrieved {len(citations)} passage(s).",
                }
            )

        system = _SYSTEM_TEMPLATE.format(memory=memory_block, context=context_text or "(none)")
        completion = await llm.complete(
            [LLMMessage("system", system), LLMMessage("user", objective)]
        )
        answer_text = completion.text
        total_tokens = completion.total_tokens
        record_llm_usage(
            total_tokens,
            total_tokens / 1000 * settings.llm_cost_per_1k_tokens,
        )
        steps.append(
            {
                "step": len(steps) + 1,
                "thought": "Synthesise a grounded answer from the passages.",
                "action": "final_answer",
                "observation": "Answer generated.",
            }
        )
        status = AgentRunStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001 - recorded on the run for audit
        status = AgentRunStatus.FAILED
        error = str(exc)

    answer_message_id: uuid.UUID | None = None
    if status is AgentRunStatus.COMPLETED:
        assistant = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            tokens=total_tokens,
            citations=citations or None,
        )
        db.add(assistant)
        await db.flush()
        answer_message_id = assistant.id
        if settings.agent_memory_enabled and memory_vector is not None:
            memory.get_agent_memory().remember(
                conversation.workspace_id,
                memory_vector,
                f"Objective: {objective} | Answer: {answer_text}",
            )

    run = AgentRun(
        conversation_id=conversation_id,
        status=status,
        objective=objective,
        steps=steps,
        tool_calls=tool_calls,
        cost_usd=round(total_tokens / 1000 * settings.llm_cost_per_1k_tokens, 6),
        latency_ms=int((time.perf_counter() - started) * 1000),
        answer_message_id=answer_message_id,
        error=error,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def list_runs(db: AsyncSession, conversation_id: uuid.UUID) -> list[AgentRun]:
    """Return a conversation's agent runs, newest first."""
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.conversation_id == conversation_id)
        .order_by(AgentRun.created_at.desc())
    )
    return list(result.scalars().all())


async def get_run(
    db: AsyncSession, conversation_id: uuid.UUID, run_id: uuid.UUID
) -> AgentRun | None:
    """Return a single agent run scoped to its conversation, or ``None``."""
    run = await db.get(AgentRun, run_id)
    if run is None or run.conversation_id != conversation_id:
        return None
    return run
