"""User persistence and authentication logic."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.services.exceptions import EmailAlreadyExists, InvalidCredentials


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    """Return an active user by email, or ``None``."""
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Return an active user by id, or ``None``."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str | None = None,
) -> User:
    """Create a new user, enforcing email uniqueness."""
    if await get_by_email(db, email) is not None:
        raise EmailAlreadyExists(email)

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    """Return the user if credentials are valid, else raise."""
    user = await get_by_email(db, email)
    if user is None or not user.is_active:
        raise InvalidCredentials(email)
    if not verify_password(password, user.hashed_password):
        raise InvalidCredentials(email)
    return user
