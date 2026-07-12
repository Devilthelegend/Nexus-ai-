"""Workspace and membership logic with tenant isolation and RBAC."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Role
from app.models.membership import Membership
from app.models.user import User
from app.models.workspace import Workspace
from app.services.exceptions import NotFoundError, PermissionDenied

# Roles permitted to manage workspace membership.
_MANAGER_ROLES = frozenset({Role.OWNER, Role.ADMIN})


async def create_workspace(db: AsyncSession, name: str, owner: User) -> Workspace:
    """Create a workspace and grant the creator the OWNER role."""
    workspace = Workspace(name=name, owner_id=owner.id)
    db.add(workspace)
    await db.flush()

    db.add(
        Membership(
            user_id=owner.id, workspace_id=workspace.id, role=Role.OWNER
        )
    )
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def list_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Workspace]:
    """Return every non-deleted workspace the user is a member of."""
    result = await db.execute(
        select(Workspace)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id, Workspace.deleted_at.is_(None))
    )
    return list(result.scalars().all())


async def get_membership(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> Membership | None:
    """Return the caller's membership in a workspace, or ``None``."""
    result = await db.execute(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_for_user(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> Workspace:
    """Return a workspace only if the user is a member (tenant isolation)."""
    if await get_membership(db, workspace_id, user_id) is None:
        raise NotFoundError("workspace")
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError("workspace")
    return workspace


async def add_member(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    user_id: uuid.UUID,
    role: Role,
) -> Membership:
    """Add or update a member; requires the actor to be OWNER or ADMIN."""
    actor = await get_membership(db, workspace_id, actor_id)
    if actor is None:
        raise NotFoundError("workspace")
    if actor.role not in _MANAGER_ROLES:
        raise PermissionDenied("insufficient role to manage members")

    existing = await get_membership(db, workspace_id, user_id)
    if existing is not None:
        existing.role = role
        await db.commit()
        await db.refresh(existing)
        return existing

    membership = Membership(
        user_id=user_id, workspace_id=workspace_id, role=role
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership
