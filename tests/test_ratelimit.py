"""Tests for the fixed-window rate limiting middleware."""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings

_AUTH = "/api/v1/auth"
_PASSWORD = "s3cret-password"


@pytest.fixture(autouse=True)
def reset_rate_limit_settings():
    """Restore rate-limit settings after each test (cached singleton)."""
    settings = get_settings()
    original = (
        settings.rate_limit_enabled,
        settings.rate_limit_requests,
        settings.rate_limit_window_seconds,
    )
    yield
    (
        settings.rate_limit_enabled,
        settings.rate_limit_requests,
        settings.rate_limit_window_seconds,
    ) = original


async def _token(client: AsyncClient, email: str) -> str:
    await client.post(
        f"{_AUTH}/register", json={"email": email, "password": _PASSWORD}
    )
    login = await client.post(
        f"{_AUTH}/login", json={"email": email, "password": _PASSWORD}
    )
    return login.json()["access_token"]


async def test_requests_over_limit_are_throttled(
    client: AsyncClient, monkeypatch
) -> None:
    token = await _token(client, "rl-user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_requests", 3)

    statuses = [
        (await client.get(f"{_AUTH}/me", headers=headers)).status_code
        for _ in range(4)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429


async def test_throttled_response_sets_retry_after(
    client: AsyncClient, monkeypatch
) -> None:
    token = await _token(client, "rl-retry@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)

    await client.get(f"{_AUTH}/me", headers=headers)
    blocked = await client.get(f"{_AUTH}/me", headers=headers)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


async def test_health_endpoints_are_exempt(
    client: AsyncClient, monkeypatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)

    statuses = [
        (await client.get("/healthz")).status_code for _ in range(5)
    ]
    assert statuses == [200, 200, 200, 200, 200]


async def test_disabled_limiter_allows_all(
    client: AsyncClient, monkeypatch
) -> None:
    token = await _token(client, "rl-off@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)

    statuses = [
        (await client.get(f"{_AUTH}/me", headers=headers)).status_code
        for _ in range(4)
    ]
    assert statuses == [200, 200, 200, 200]
