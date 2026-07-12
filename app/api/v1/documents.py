"""Document endpoints: upload, list, retrieve, status, delete and reprocess.

Documents are always scoped to a workspace; tenant isolation and RBAC are
enforced in the service layer via workspace membership checks.
"""

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession, Embedder, Vectors
from app.core.config import get_settings
from app.schemas.document import DocumentRead, DocumentStatusRead
from app.services import document_service
from app.services.exceptions import NotFoundError

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])

_NOT_FOUND = "Document not found"


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    embedder: Embedder,
    store: Vectors,
    file: UploadFile = File(...),
) -> DocumentRead:
    """Upload a file and (eagerly, by default) ingest it into the index."""
    settings = get_settings()
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")

    try:
        document = await document_service.create_document(
            db,
            workspace_id=workspace_id,
            user_id=current_user.id,
            filename=file.filename or "upload",
            mime_type=file.content_type or "application/octet-stream",
            data=data,
            embedder=embedder,
            store=store,
            settings=settings,
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found") from exc
    return DocumentRead.model_validate(document)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    workspace_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[DocumentRead]:
    """List non-deleted documents in a workspace the caller can access."""
    try:
        items = await document_service.list_for_workspace(db, workspace_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found") from exc
    return [DocumentRead.model_validate(d) for d in items]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> DocumentRead:
    """Retrieve a single document."""
    try:
        document = await document_service.get_for_user(
            db, workspace_id, document_id, current_user.id
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/status", response_model=DocumentStatusRead)
async def get_document_status(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> DocumentStatusRead:
    """Return the ingestion status of a document (for polling)."""
    try:
        document = await document_service.get_for_user(
            db, workspace_id, document_id, current_user.id
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc
    return DocumentStatusRead.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    store: Vectors,
) -> None:
    """Soft-delete a document and purge its vectors."""
    try:
        await document_service.delete_document(
            db, workspace_id, document_id, current_user.id, store
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc


@router.post("/{document_id}/reprocess", response_model=DocumentRead)
async def reprocess_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    embedder: Embedder,
    store: Vectors,
) -> DocumentRead:
    """Replay ingestion for a document (dead-letter retry)."""
    try:
        document = await document_service.reprocess_document(
            db, workspace_id, document_id, current_user.id, embedder, store
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc
    return DocumentRead.model_validate(document)
