"""Conversation and RAG chat endpoints (workspace-scoped)."""

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import LLM, CurrentUser, DbSession, Embedder, Vectors
from app.schemas.conversation import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationRead,
    MessageRead,
)
from app.services import chat_service, conversation_service
from app.services.exceptions import NotFoundError

router = APIRouter(prefix="/workspaces/{workspace_id}/conversations", tags=["conversations"])

_NOT_FOUND = "Conversation not found"


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    workspace_id: uuid.UUID,
    payload: ConversationCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ConversationRead:
    """Start a new conversation in a workspace."""
    try:
        conversation = await conversation_service.create_conversation(
            db, workspace_id, current_user.id, payload.title
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found") from exc
    return ConversationRead.model_validate(conversation)


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    workspace_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[ConversationRead]:
    """List the caller's conversations in a workspace."""
    try:
        items = await conversation_service.list_for_user(db, workspace_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found") from exc
    return [ConversationRead.model_validate(c) for c in items]


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ConversationRead:
    """Retrieve a single conversation."""
    try:
        conversation = await conversation_service.get_for_user(
            db, workspace_id, conversation_id, current_user.id
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc
    return ConversationRead.model_validate(conversation)


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
async def list_messages(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[MessageRead]:
    """Return the message history of a conversation."""
    try:
        await conversation_service.get_for_user(db, workspace_id, conversation_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc
    messages = await conversation_service.list_messages(db, conversation_id)
    return [MessageRead.model_validate(m) for m in messages]


@router.post("/{conversation_id}/messages", response_model=ChatResponse)
async def post_message(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatRequest,
    db: DbSession,
    current_user: CurrentUser,
    embedder: Embedder,
    store: Vectors,
    llm: LLM,
) -> ChatResponse:
    """Submit a user message and return the grounded assistant answer."""
    try:
        conversation = await conversation_service.get_for_user(
            db, workspace_id, conversation_id, current_user.id
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc

    answer = await chat_service.generate_answer(
        db,
        conversation=conversation,
        message=payload.message,
        embedder=embedder,
        store=store,
        llm=llm,
    )
    return ChatResponse(
        conversation_id=conversation_id,
        answer=MessageRead.model_validate(answer),
    )


@router.post("/{conversation_id}/messages/stream")
async def post_message_stream(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatRequest,
    db: DbSession,
    current_user: CurrentUser,
    embedder: Embedder,
    store: Vectors,
    llm: LLM,
) -> StreamingResponse:
    """Stream the grounded assistant answer as Server-Sent Events."""
    try:
        conversation = await conversation_service.get_for_user(
            db, workspace_id, conversation_id, current_user.id
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from exc

    async def event_stream() -> AsyncIterator[str]:
        async for event in chat_service.stream_answer(
            db,
            conversation=conversation,
            message=payload.message,
            embedder=embedder,
            store=store,
            llm=llm,
        ):
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
