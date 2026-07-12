"""Document ingestion schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus


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
