"""Authentication schemas."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Payload for creating a new user account."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    """Payload for password-based login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Payload for exchanging a refresh token for new tokens."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Issued access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
