"""Authentication endpoints: register, login, refresh and current user."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services import auth_service
from app.services.exceptions import EmailAlreadyExists, InvalidCredentials

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DbSession) -> UserRead:
    """Create a new user account."""
    try:
        user = await auth_service.register(db, payload.email, payload.password, payload.full_name)
    except EmailAlreadyExists as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from exc
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    """Authenticate with email and password to obtain tokens."""
    try:
        return await auth_service.login(db, payload.email, payload.password)
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from exc


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    """Exchange a valid refresh token for a new token pair (rotating it)."""
    try:
        return await auth_service.refresh(db, payload.refresh_token)
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: DbSession) -> None:
    """Revoke a refresh token so it can no longer be exchanged."""
    try:
        await auth_service.logout(db, payload.refresh_token)
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    """Return the currently authenticated user."""
    return UserRead.model_validate(current_user)
