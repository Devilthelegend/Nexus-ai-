"""Tool abstraction for the agent orchestrator.

A tool is a named, described capability the agent may invoke during a run. The
knowledge-base tool reuses the existing hybrid retrieval service so the agent
grounds its answers in the same workspace-scoped context as RAG chat.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.vectorstore.base import VectorStore
from app.core.config import Settings
from app.services import retrieval


@dataclass(slots=True)
class ToolContext:
    """Everything a tool needs to execute within a workspace boundary."""

    db: AsyncSession
    workspace_id: uuid.UUID
    embedder: EmbeddingProvider
    store: VectorStore
    settings: Settings


@dataclass(slots=True)
class ToolResult:
    """A tool's textual output plus any structured data it produced."""

    output: str
    data: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class Tool(Protocol):
    """A capability the agent can invoke by name."""

    name: str
    description: str

    async def run(self, context: ToolContext, query: str) -> ToolResult:
        """Execute the tool for ``query`` and return its result."""
        ...


class KnowledgeBaseSearchTool:
    """Search the workspace knowledge base via hybrid retrieval."""

    name = "knowledge_base_search"
    description = (
        "Search the workspace knowledge base and return grounded passages "
        "with citations relevant to the query."
    )

    async def run(self, context: ToolContext, query: str) -> ToolResult:
        result = await retrieval.retrieve(
            context.db,
            workspace_id=context.workspace_id,
            query=query,
            embedder=context.embedder,
            store=context.store,
            settings=context.settings,
        )
        return ToolResult(output=result.context, data=result.citations)
