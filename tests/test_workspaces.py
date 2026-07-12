"""Tests for workspace CRUD, RBAC and multi-tenant isolation."""

from httpx import AsyncClient

_AUTH = "/api/v1/auth"
_WS = "/api/v1/workspaces"
_PASSWORD = "s3cret-password"


async def _make_user(client: AsyncClient, email: str) -> dict[str, object]:
    """Register and log in a user; return id and bearer auth headers."""
    register = await client.post(f"{_AUTH}/register", json={"email": email, "password": _PASSWORD})
    assert register.status_code == 201, register.text
    user_id = register.json()["id"]

    login = await client.post(f"{_AUTH}/login", json={"email": email, "password": _PASSWORD})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"id": user_id, "headers": {"Authorization": f"Bearer {token}"}}


async def test_create_workspace_makes_creator_owner(client: AsyncClient) -> None:
    owner = await _make_user(client, "owner@example.com")

    response = await client.post(_WS, json={"name": "Acme"}, headers=owner["headers"])
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme"
    assert body["owner_id"] == owner["id"]
    assert body["plan"] == "free"


async def test_create_workspace_requires_auth(client: AsyncClient) -> None:
    response = await client.post(_WS, json={"name": "NoAuth"})
    assert response.status_code in (401, 403)


async def test_list_only_returns_own_workspaces(client: AsyncClient) -> None:
    owner = await _make_user(client, "list-owner@example.com")
    other = await _make_user(client, "list-other@example.com")

    await client.post(_WS, json={"name": "Owned"}, headers=owner["headers"])

    owned = await client.get(_WS, headers=owner["headers"])
    assert owned.status_code == 200
    assert len(owned.json()) == 1

    # A different tenant must not see the workspace.
    others = await client.get(_WS, headers=other["headers"])
    assert others.status_code == 200
    assert others.json() == []


async def test_get_workspace_hidden_from_non_member(client: AsyncClient) -> None:
    owner = await _make_user(client, "iso-owner@example.com")
    outsider = await _make_user(client, "iso-outsider@example.com")

    created = await client.post(_WS, json={"name": "Private"}, headers=owner["headers"])
    workspace_id = created.json()["id"]

    # Owner can read it.
    ok = await client.get(f"{_WS}/{workspace_id}", headers=owner["headers"])
    assert ok.status_code == 200

    # Outsider gets a 404 (isolation hides existence).
    hidden = await client.get(f"{_WS}/{workspace_id}", headers=outsider["headers"])
    assert hidden.status_code == 404


async def test_owner_can_add_member(client: AsyncClient) -> None:
    owner = await _make_user(client, "add-owner@example.com")
    member = await _make_user(client, "add-member@example.com")

    created = await client.post(_WS, json={"name": "Team"}, headers=owner["headers"])
    workspace_id = created.json()["id"]

    response = await client.post(
        f"{_WS}/{workspace_id}/members",
        json={"user_id": member["id"], "role": "member"},
        headers=owner["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == member["id"]
    assert body["role"] == "member"

    # The added member can now see the workspace.
    seen = await client.get(f"{_WS}/{workspace_id}", headers=member["headers"])
    assert seen.status_code == 200


async def test_member_cannot_add_members(client: AsyncClient) -> None:
    owner = await _make_user(client, "rbac-owner@example.com")
    member = await _make_user(client, "rbac-member@example.com")
    outsider = await _make_user(client, "rbac-outsider@example.com")

    created = await client.post(_WS, json={"name": "Guarded"}, headers=owner["headers"])
    workspace_id = created.json()["id"]

    await client.post(
        f"{_WS}/{workspace_id}/members",
        json={"user_id": member["id"], "role": "member"},
        headers=owner["headers"],
    )

    # A plain member lacks permission to manage membership.
    response = await client.post(
        f"{_WS}/{workspace_id}/members",
        json={"user_id": outsider["id"], "role": "member"},
        headers=member["headers"],
    )
    assert response.status_code == 403


async def test_non_member_cannot_add_members(client: AsyncClient) -> None:
    owner = await _make_user(client, "nm-owner@example.com")
    outsider = await _make_user(client, "nm-outsider@example.com")

    created = await client.post(_WS, json={"name": "Sealed"}, headers=owner["headers"])
    workspace_id = created.json()["id"]

    # A non-member acting on the workspace sees a 404, not the members list.
    response = await client.post(
        f"{_WS}/{workspace_id}/members",
        json={"user_id": outsider["id"], "role": "member"},
        headers=outsider["headers"],
    )
    assert response.status_code == 404
