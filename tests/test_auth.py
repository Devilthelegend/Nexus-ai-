"""Tests for registration, login, token refresh and the current-user route."""

from httpx import AsyncClient

_PREFIX = "/api/v1/auth"


async def _register(client: AsyncClient, email: str, password: str = "s3cret-password") -> None:
    response = await client.post(
        f"{_PREFIX}/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text


async def test_register_returns_public_user(client: AsyncClient) -> None:
    response = await client.post(
        f"{_PREFIX}/register",
        json={"email": "alice@example.com", "password": "s3cret-password"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["is_active"] is True
    assert "id" in body
    # The hashed password must never be exposed.
    assert "hashed_password" not in body
    assert "password" not in body


async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    await _register(client, "dup@example.com")
    response = await client.post(
        f"{_PREFIX}/register",
        json={"email": "dup@example.com", "password": "s3cret-password"},
    )
    assert response.status_code == 409


async def test_login_returns_token_pair(client: AsyncClient) -> None:
    await _register(client, "bob@example.com")
    response = await client.post(
        f"{_PREFIX}/login",
        json={"email": "bob@example.com", "password": "s3cret-password"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
    await _register(client, "carol@example.com")
    response = await client.post(
        f"{_PREFIX}/login",
        json={"email": "carol@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_login_unknown_user_rejected(client: AsyncClient) -> None:
    response = await client.post(
        f"{_PREFIX}/login",
        json={"email": "ghost@example.com", "password": "s3cret-password"},
    )
    assert response.status_code == 401


async def test_refresh_issues_new_tokens(client: AsyncClient) -> None:
    await _register(client, "dave@example.com")
    login = await client.post(
        f"{_PREFIX}/login",
        json={"email": "dave@example.com", "password": "s3cret-password"},
    )
    refresh_token = login.json()["refresh_token"]

    response = await client.post(f"{_PREFIX}/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_refresh_rejects_access_token(client: AsyncClient) -> None:
    await _register(client, "erin@example.com")
    login = await client.post(
        f"{_PREFIX}/login",
        json={"email": "erin@example.com", "password": "s3cret-password"},
    )
    access_token = login.json()["access_token"]

    # An access token must not be accepted where a refresh token is required.
    response = await client.post(f"{_PREFIX}/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


async def test_refresh_rejects_garbage(client: AsyncClient) -> None:
    response = await client.post(f"{_PREFIX}/refresh", json={"refresh_token": "not-a-jwt"})
    assert response.status_code == 401


async def _login_tokens(client: AsyncClient, email: str) -> dict[str, str]:
    await _register(client, email)
    login = await client.post(
        f"{_PREFIX}/login",
        json={"email": email, "password": "s3cret-password"},
    )
    return login.json()


async def test_refresh_rotates_and_invalidates_old_token(
    client: AsyncClient,
) -> None:
    tokens = await _login_tokens(client, "rotate@example.com")
    old_refresh = tokens["refresh_token"]

    first = await client.post(f"{_PREFIX}/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    assert first.json()["refresh_token"] != old_refresh

    # The rotated (old) token must no longer be accepted.
    reuse = await client.post(f"{_PREFIX}/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    tokens = await _login_tokens(client, "logout@example.com")
    refresh_token = tokens["refresh_token"]

    logout = await client.post(f"{_PREFIX}/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204

    after = await client.post(f"{_PREFIX}/refresh", json={"refresh_token": refresh_token})
    assert after.status_code == 401


async def test_logout_rejects_unknown_token(client: AsyncClient) -> None:
    response = await client.post(f"{_PREFIX}/logout", json={"refresh_token": "not-a-jwt"})
    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{_PREFIX}/me")
    assert response.status_code in (401, 403)


async def test_me_returns_current_user(client: AsyncClient) -> None:
    await _register(client, "frank@example.com")
    login = await client.post(
        f"{_PREFIX}/login",
        json={"email": "frank@example.com", "password": "s3cret-password"},
    )
    access_token = login.json()["access_token"]

    response = await client.get(
        f"{_PREFIX}/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "frank@example.com"
