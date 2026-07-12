"""Document model: an uploaded file tracked through the ingestion lifecycle."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin
from app.models.enums import DocumentStatus

if TYPE_CHECKING:
    from app.models.chunk import Chunk


class Document(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A workspace-scoped uploaded file and its ingestion status.

    ``checksum`` is unique per workspace, giving idempotent ingestion: the same
    content uploaded twice resolves to the existing document.
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "checksum", name="uq_workspace_checksum"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status"),
        default=DocumentStatus.QUEUED,
        nullable=False,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
