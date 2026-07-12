"""Agent orchestration schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentRunStatus
from app.schemas.conversation import MessageRead


class AgentRunRequest(BaseModel):
    """An objective submitted to the agent for a conversation."""

    objective: str = Field(min_length=1)


class AgentRunRead(BaseModel):
    """Public representation of an agent run and its recorded metrics."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    status: AgentRunStatus
    objective: str
    steps: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    cost_usd: float
    latency_ms: int
    answer_message_id: uuid.UUID | None = None
    error: str | None = None
    created_at: datetime


class AgentRunResponse(BaseModel):
    """The completed run together with the grounded assistant answer."""

    run: AgentRunRead
    answer: MessageRead | None = None
