"""Shared FastAPI dependencies: DB session and the authenticated user."""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingProvider, get_embedding_provider
from app.ai.llm import LLMProvider, get_llm_provider
from app.ai.vectorstore import VectorStore, get_vector_store
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.services import user_service

_bearer = HTTPBearer(auto_error=True)

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_embedder() -> EmbeddingProvider:
    """Resolve the configured embedding provider."""
    return get_embedding_provider()


def get_vectors() -> VectorStore:
    """Resolve the configured vector store."""
    return get_vector_store()


def get_llm() -> LLMProvider:
    """Resolve the configured LLM provider."""
    return get_llm_provider()


Embedder = Annotated[EmbeddingProvider, Depends(get_embedder)]
Vectors = Annotated[VectorStore, Depends(get_vectors)]
LLM = Annotated[LLMProvider, Depends(get_llm)]

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> User:
    """Resolve and return the user identified by a valid access token."""
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _CREDENTIALS_ERROR from exc

    if payload.get("type") != "access":
        raise _CREDENTIALS_ERROR

    subject = payload.get("sub")
    if not subject:
        raise _CREDENTIALS_ERROR

    user = await user_service.get_by_id(db, uuid.UUID(subject))
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
