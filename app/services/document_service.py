"""Document lifecycle: upload, retrieval, deletion and reprocessing.

Enforces tenant isolation by requiring workspace membership on every access,
and idempotent ingestion via a per-workspace content checksum. Raw bytes are
persisted to ``upload_dir`` so failed documents can be replayed from the DLQ.
"""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.vectorstore.base import VectorStore
from app.core.config import Settings, get_settings
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.services import workspace_service
from app.services.exceptions import NotFoundError
from app.services.ingestion.pipeline import run_ingestion


def compute_checksum(data: bytes) -> str:
    """Return the SHA-256 hex digest used for idempotent ingestion."""
    return hashlib.sha256(data).hexdigest()


def _storage_path(settings: Settings, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Path:
    base = Path(settings.upload_dir) / str(workspace_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / str(document_id)


async def _require_membership(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if await workspace_service.get_membership(db, workspace_id, user_id) is None:
        raise NotFoundError("workspace")


async def _get_by_checksum(
    db: AsyncSession, workspace_id: uuid.UUID, checksum: str
) -> Document | None:
    result = await db.execute(
        select(Document).where(
            Document.workspace_id == workspace_id,
            Document.checksum == checksum,
            Document.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_document(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    filename: str,
    mime_type: str,
    data: bytes,
    embedder: EmbeddingProvider,
    store: VectorStore,
    settings: Settings | None = None,
) -> Document:
    """Create (or return the existing) document and optionally ingest it."""
    settings = settings or get_settings()
    await _require_membership(db, workspace_id, user_id)

    checksum = compute_checksum(data)
    existing = await _get_by_checksum(db, workspace_id, checksum)
    if existing is not None:
        return existing

    document = Document(
        workspace_id=workspace_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        checksum=checksum,
        status=DocumentStatus.QUEUED,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    _storage_path(settings, workspace_id, document.id).write_bytes(data)

    if settings.ingest_eager:
        await run_ingestion(db, document, data, embedder, store, settings)
    return document


async def get_for_user(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Document:
    """Return a document only if the caller is a member of its workspace."""
    await _require_membership(db, workspace_id, user_id)
    document = await db.get(Document, document_id)
    if document is None or document.deleted_at is not None or document.workspace_id != workspace_id:
        raise NotFoundError("document")
    return document


async def list_for_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[Document]:
    """Return every non-deleted document in a workspace the user can access."""
    await _require_membership(db, workspace_id, user_id)
    result = await db.execute(
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_document(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    store: VectorStore,
) -> None:
    """Soft-delete a document and purge its vectors from the store."""
    document = await get_for_user(db, workspace_id, document_id, user_id)
    await store.delete_by_document(workspace_id, document_id)
    document.deleted_at = datetime.now(UTC)
    await db.commit()


async def reprocess_document(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    embedder: EmbeddingProvider,
    store: VectorStore,
    settings: Settings | None = None,
) -> Document:
    """Replay ingestion for a document from its stored bytes (DLQ retry)."""
    settings = settings or get_settings()
    document = await get_for_user(db, workspace_id, document_id, user_id)
    data = _storage_path(settings, workspace_id, document_id).read_bytes()
    return await run_ingestion(db, document, data, embedder, store, settings)
