"""AgentRun model: an auditable record of one agent orchestration run.

Captures the objective, the ordered reasoning ``steps`` and ``tool_calls`` the
agent made, the grounded answer message it produced, and cost/latency metrics
for observability. Runs are scoped to a conversation (its tenant boundary).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AgentRunStatus


class AgentRun(Base, UUIDMixin, TimestampMixin):
    """One bounded agent execution against a conversation's knowledge base."""

    __tablename__ = "agent_runs"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(AgentRunStatus, name="agent_run_status"), nullable=False
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    cost_usd: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    answer_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
