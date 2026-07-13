"""Document ingestion schemas."""

import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.models.enums import DocumentStatus


class DocumentFromUrlRequest(BaseModel):
    """Payload for ingesting a document from a public ``http(s)`` URL."""

    url: AnyHttpUrl
    filename: str | None = Field(default=None, max_length=255)


class DocumentRead(BaseModel):
    """Public representation of an uploaded document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    checksum: str
    status: DocumentStatus
    chunk_count: int
    error: str | None
    created_at: datetime


class DocumentStatusRead(BaseModel):
    """Lightweight status view for polling ingestion progress."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: DocumentStatus
    chunk_count: int
    error: str | None
