"""Shared enumerations for domain models."""

from enum import StrEnum


class Role(StrEnum):
    """Workspace membership roles, ordered from most to least privileged."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class DocumentStatus(StrEnum):
    """Lifecycle states for an ingested document."""

    QUEUED = "queued"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class MessageRole(StrEnum):
    """Author role for a conversation message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class AgentRunStatus(StrEnum):
    """Lifecycle states for an agent orchestration run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
