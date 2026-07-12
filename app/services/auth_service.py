"""Authentication orchestration: registration, login, refresh and logout.

Refresh tokens are tracked server-side (by ``jti``) so that refresh rotates the
presented token and logout revokes it; a revoked or rotated token can no longer
be exchanged.
"""

import uuid

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.services import token_service, user_service
from app.services.exceptions import InvalidCredentials


async def _issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    """Issue an access/refresh pair and record the refresh token (no commit)."""
    subject = str(user.id)
    jti = uuid.uuid4()
    await token_service.persist(db, user_id=user.id, jti=jti)
    return TokenResponse(
        access_token=create_access_token(subject),
        refresh_token=create_refresh_token(subject, str(jti)),
    )


def _decode_refresh(refresh_token: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Validate a refresh JWT and return its (subject, jti) as UUIDs."""
    try:
        payload = decode_token(refresh_token)
    except jwt.PyJWTError as exc:
        raise InvalidCredentials("invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise InvalidCredentials("not a refresh token")

    subject = payload.get("sub")
    jti = payload.get("jti")
    if not subject or not jti:
        raise InvalidCredentials("malformed refresh token")
    try:
        return uuid.UUID(subject), uuid.UUID(jti)
    except ValueError as exc:
        raise InvalidCredentials("malformed refresh token") from exc


async def register(
    db: AsyncSession, email: str, password: str, full_name: str | None
) -> User:
    """Create a new user account."""
    return await user_service.create_user(db, email, password, full_name)


async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    """Authenticate a user and issue tokens."""
    user = await user_service.authenticate(db, email, password)
    tokens = await _issue_tokens(db, user)
    await db.commit()
    return tokens


async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
    """Exchange a valid refresh token for a new pair, rotating the old one."""
    subject, jti = _decode_refresh(refresh_token)

    stored = await token_service.get_active(db, jti)
    if stored is None or stored.user_id != subject:
        raise InvalidCredentials("refresh token is not active")

    user = await user_service.get_by_id(db, subject)
    if user is None or not user.is_active:
        raise InvalidCredentials("user not found or inactive")

    await token_service.revoke(db, stored)
    tokens = await _issue_tokens(db, user)
    await db.commit()
    return tokens


async def logout(db: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh token so it can no longer be exchanged."""
    _, jti = _decode_refresh(refresh_token)
    stored: RefreshToken | None = await token_service.get_active(db, jti)
    if stored is None:
        raise InvalidCredentials("refresh token is not active")
    await token_service.revoke(db, stored)
    await db.commit()
