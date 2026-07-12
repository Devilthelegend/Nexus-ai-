"""Workspace and membership schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Role


class WorkspaceCreate(BaseModel):
    """Payload for creating a workspace."""

    name: str = Field(min_length=1, max_length=255)


class WorkspaceRead(BaseModel):
    """Public representation of a workspace."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    plan: str
    created_at: datetime


class MemberAdd(BaseModel):
    """Payload for adding a member to a workspace."""

    user_id: uuid.UUID
    role: Role = Role.MEMBER


class MembershipRead(BaseModel):
    """Public representation of a workspace membership."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role
