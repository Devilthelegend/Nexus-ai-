"""Ingestion orchestration: extract -> chunk -> embed -> index.

The pipeline drives a document through its lifecycle and records failures on the
document itself (``status=failed`` with an ``error`` message). Failed documents
form an application-level dead-letter queue that the reprocess path can replay.
"""

import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.vectorstore.base import VectorRecord, VectorStore
from app.core.config import Settings, get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.embedding import Embedding
from app.models.enums import DocumentStatus
from app.services.ingestion import extractors
from app.services.ingestion.chunker import chunk_pages

logger = logging.getLogger(__name__)


def _batches(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def run_ingestion(
    db: AsyncSession,
    document: Document,
    data: bytes,
    embedder: EmbeddingProvider,
    store: VectorStore,
    settings: Settings | None = None,
) -> Document:
    """Process a document end to end, updating its status in place."""
    settings = settings or get_settings()

    # Capture identifiers up front: after a rollback the ORM instance is
    # expired, and lazy-loading attributes in async mode would fail.
    document_id = document.id
    workspace_id = document.workspace_id
    filename = document.filename

    document.status = DocumentStatus.PROCESSING
    document.error = None
    await db.commit()

    try:
        pages = extractors.extract(filename, data)
        chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise ValueError("no extractable text found in document")

        # Clear any prior artifacts (supports idempotent reprocessing).
        await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        await store.delete_by_document(workspace_id, document_id)

        chunk_rows = [
            Chunk(
                document_id=document_id,
                ordinal=c.ordinal,
                text=c.text,
                token_count=c.token_count,
                page=c.page,
                section=c.section,
            )
            for c in chunks
        ]
        db.add_all(chunk_rows)
        await db.flush()

        await store.ensure_ready(embedder.dimension)
        records: list[VectorRecord] = []
        for batch in _batches([r.text for r in chunk_rows], settings.embedding_batch_size):
            vectors = await embedder.embed(batch)
            offset = len(records)
            for local, vector in enumerate(vectors):
                row = chunk_rows[offset + local]
                vector_id = str(row.id)
                db.add(
                    Embedding(
                        chunk_id=row.id,
                        vector_id=vector_id,
                        model=embedder.model,
                        dimension=embedder.dimension,
                    )
                )
                records.append(
                    VectorRecord(
                        id=vector_id,
                        vector=vector,
                        payload={
                            "workspace_id": str(workspace_id),
                            "document_id": str(document_id),
                            "chunk_id": vector_id,
                            "ordinal": row.ordinal,
                            "page": row.page,
                            "section": row.section,
                            "text": row.text,
                        },
                    )
                )

        await store.upsert(records)

        document.chunk_count = len(chunk_rows)
        document.status = DocumentStatus.INDEXED
        document.error = None
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - recorded as a DLQ entry
        await db.rollback()
        document.status = DocumentStatus.FAILED
        document.error = str(exc)
        document.chunk_count = 0
        await db.commit()
        logger.warning(
            "ingestion failed for document %s: %s", document_id, exc
        )

    await db.refresh(document)
    return document
