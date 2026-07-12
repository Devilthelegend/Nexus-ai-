"""Persistence models (SQLAlchemy).

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogeneration and test table creation see the full schema.
"""

from app.db.base import Base
from app.models.agent_run import AgentRun
from app.models.chunk import Chunk
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.embedding import Embedding
from app.models.enums import AgentRunStatus, DocumentStatus, MessageRole, Role
from app.models.membership import Membership
from app.models.message import Message
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.workspace import Workspace

__all__ = [
    "AgentRun",
    "AgentRunStatus",
    "Base",
    "Chunk",
    "Conversation",
    "Document",
    "DocumentStatus",
    "Embedding",
    "Membership",
    "Message",
    "MessageRole",
    "RefreshToken",
    "Role",
    "User",
    "Workspace",
]

metadata = Base.metadata
