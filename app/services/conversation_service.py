"""Conversation lifecycle with tenant isolation and per-user ownership."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.services import workspace_service
from app.services.exceptions import NotFoundError


async def _require_membership(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if await workspace_service.get_membership(db, workspace_id, user_id) is None:
        raise NotFoundError("workspace")


async def create_conversation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str,
) -> Conversation:
    """Start a conversation owned by the caller within a workspace."""
    await _require_membership(db, workspace_id, user_id)
    conversation = Conversation(
        workspace_id=workspace_id, user_id=user_id, title=title
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_for_user(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[Conversation]:
    """List the caller's conversations within a workspace."""
    await _require_membership(db, workspace_id, user_id)
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.user_id == user_id,
        )
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


async def get_for_user(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Conversation:
    """Return a conversation only if owned by the caller in the workspace."""
    await _require_membership(db, workspace_id, user_id)
    conversation = await db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.workspace_id != workspace_id
        or conversation.user_id != user_id
    ):
        raise NotFoundError("conversation")
    return conversation


async def list_messages(
    db: AsyncSession, conversation_id: uuid.UUID
) -> list[Message]:
    """Return every message in a conversation, oldest first."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())
