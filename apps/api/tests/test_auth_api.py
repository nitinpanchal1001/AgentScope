from httpx import AsyncClient


async def test_register_login_refresh_rotation_and_reuse(client: AsyncClient) -> None:
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.com",
            "password": "correct-horse-42",
            "display_name": "Owner",
        },
    )
    assert registered.status_code == 201
    first_refresh = registered.cookies["agentscope_refresh"]
    assert first_refresh not in registered.text
    cookie = next(item for item in registered.cookies.jar if item.name == "agentscope_refresh")
    assert cookie.has_nonstandard_attr("HttpOnly")

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {registered.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    second_refresh = refreshed.cookies["agentscope_refresh"]
    assert second_refresh != first_refresh

    client.cookies.set("agentscope_refresh", first_refresh, path="/api/v1/auth")
    reused = await client.post("/api/v1/auth/refresh")
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    client.cookies.set("agentscope_refresh", second_refresh, path="/api/v1/auth")
    family_revoked = await client.post("/api/v1/auth/refresh")
    assert family_revoked.status_code == 401


async def test_duplicate_registration_uses_consistent_error_shape(client: AsyncClient) -> None:
    payload = {"email": "same@example.com", "password": "correct-horse-42", "display_name": "Same"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    duplicate = await client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RESOURCE_CONFLICT"
    assert duplicate.headers["x-request-id"]
