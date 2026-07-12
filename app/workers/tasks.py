"""Background ingestion task.

Bridges the synchronous Celery worker to the async ingestion pipeline. A failed
run is recorded on the document (``status=failed``); those rows form the
application-level dead-letter queue that the reprocess endpoint replays.
"""

from __future__ import annotations

import asyncio
import uuid

from app.ai.embeddings import get_embedding_provider
from app.ai.vectorstore import get_vector_store
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.services.document_service import _storage_path
from app.services.ingestion.pipeline import run_ingestion
from app.workers.celery_app import celery_app


async def _ingest_document(document_id: uuid.UUID) -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, document_id)
        if document is None or document.deleted_at is not None:
            return
        data = _storage_path(
            settings, document.workspace_id, document_id
        ).read_bytes()
        await run_ingestion(
            db,
            document,
            data,
            get_embedding_provider(settings),
            get_vector_store(settings),
            settings,
        )


def ingest_document(document_id: str) -> None:
    """Synchronous entry point that drives the async pipeline to completion."""
    asyncio.run(_ingest_document(uuid.UUID(document_id)))


if celery_app is not None:  # pragma: no cover - requires Celery installed
    ingest_document = celery_app.task(
        name="app.workers.tasks.ingest_document"
    )(ingest_document)
