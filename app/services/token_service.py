"""Persistence for issued refresh tokens (rotation and revocation support).

Timestamps are compared through :func:`_as_utc` so the logic is correct on both
PostgreSQL (timezone-aware) and SQLite (naive) backends.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken


def _as_utc(value: datetime) -> datetime:
    """Coerce a possibly-naive datetime to timezone-aware UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def persist(
    db: AsyncSession, *, user_id: uuid.UUID, jti: uuid.UUID
) -> RefreshToken:
    """Record a newly issued refresh token (does not commit)."""
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    token = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
    db.add(token)
    return token


async def get_active(
    db: AsyncSession, jti: uuid.UUID
) -> RefreshToken | None:
    """Return the token for ``jti`` if it exists and is neither revoked nor expired."""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti)
    )
    token = result.scalar_one_or_none()
    if token is None or token.revoked_at is not None:
        return None
    if _as_utc(token.expires_at) <= datetime.now(timezone.utc):
        return None
    return token


async def revoke(db: AsyncSession, token: RefreshToken) -> None:
    """Mark a refresh token as revoked (does not commit)."""
    token.revoked_at = datetime.now(timezone.utc)
    db.add(token)
