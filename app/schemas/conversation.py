"""Conversation, message and RAG chat schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole


class ConversationCreate(BaseModel):
    """Payload for starting a conversation."""

    title: str = Field(min_length=1, max_length=255)


class ConversationRead(BaseModel):
    """Public representation of a conversation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime


class Citation(BaseModel):
    """A retrieved chunk that grounded an assistant answer."""

    chunk_id: str
    document_id: str
    ordinal: int | None = None
    page: int | None = None
    section: str | None = None
    score: float
    text: str


class MessageRead(BaseModel):
    """Public representation of a conversation message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    tokens: int
    citations: list[Citation] | None = None
    created_at: datetime


class ChatRequest(BaseModel):
    """A user turn submitted to a conversation."""

    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    """The grounded assistant answer for a chat turn."""

    conversation_id: uuid.UUID
    answer: MessageRead
