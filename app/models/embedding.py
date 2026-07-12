"""Embedding model: metadata for a chunk's vector stored in the vector DB.

The vector itself lives in the vector store (Qdrant); this table records the
provenance needed to locate, audit and reindex it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.chunk import Chunk


class Embedding(Base, UUIDMixin, TimestampMixin):
    """Provenance record linking a chunk to its vector in the vector store."""

    __tablename__ = "embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chunks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    vector_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)

    chunk: Mapped[Chunk] = relationship(back_populates="embedding")
