"""Workspace endpoints: create, list, retrieve and manage members."""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.workspace import (
    MemberAdd,
    MembershipRead,
    WorkspaceCreate,
    WorkspaceRead,
)
from app.services import workspace_service
from app.services.exceptions import NotFoundError, PermissionDenied

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate, db: DbSession, current_user: CurrentUser
) -> WorkspaceRead:
    """Create a workspace owned by the current user."""
    workspace = await workspace_service.create_workspace(db, payload.name, current_user)
    return WorkspaceRead.model_validate(workspace)


@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(db: DbSession, current_user: CurrentUser) -> list[WorkspaceRead]:
    """List workspaces the current user belongs to."""
    items = await workspace_service.list_for_user(db, current_user.id)
    return [WorkspaceRead.model_validate(w) for w in items]


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> WorkspaceRead:
    """Retrieve a workspace the current user is a member of."""
    try:
        workspace = await workspace_service.get_for_user(db, workspace_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found") from exc
    return WorkspaceRead.model_validate(workspace)


@router.post(
    "/{workspace_id}/members",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    workspace_id: uuid.UUID,
    payload: MemberAdd,
    db: DbSession,
    current_user: CurrentUser,
) -> MembershipRead:
    """Add or update a member (requires OWNER or ADMIN role)."""
    try:
        membership = await workspace_service.add_member(
            db, workspace_id, current_user.id, payload.user_id, payload.role
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found") from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions") from exc
    return MembershipRead.model_validate(membership)
