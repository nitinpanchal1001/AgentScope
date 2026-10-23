from conftest import register_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentscope_api.models import ApiKey


async def test_foundation_flow_and_direct_uuid_tenant_isolation(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    token_a, _ = await register_user(client, "a@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": "Org A"}, headers=headers_a
    )
    assert organization.status_code == 201
    org_id = organization.json()["id"]
    duplicate_organization = await client.post(
        "/api/v1/organizations", json={"name": "Org A"}, headers=headers_a
    )
    assert duplicate_organization.status_code == 201
    assert duplicate_organization.json()["slug"].startswith("org-a-")

    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"name": "Agent A"},
        headers=headers_a,
    )
    assert project.status_code == 201, project.text
    assert organization.json()["slug"] == "org-a"
    assert project.json()["slug"] == "agent-a"
    duplicate_project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"name": "Agent A"},
        headers=headers_a,
    )
    assert duplicate_project.status_code == 201
    assert duplicate_project.json()["slug"].startswith("agent-a-")
    project_id = project.json()["id"]
    environments = await client.get(
        f"/api/v1/projects/{project_id}/environments", headers=headers_a
    )
    assert {item["slug"] for item in environments.json()} == {
        "development",
        "staging",
        "production",
    }
    production_id = next(item["id"] for item in environments.json() if item["slug"] == "production")

    created_key = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        json={"name": "Production SDK", "environment_id": production_id},
        headers=headers_a,
    )
    assert created_key.status_code == 201, created_key.text
    raw_key = created_key.json()["key"]
    assert raw_key.startswith("as_live_")

    listed = await client.get(f"/api/v1/projects/{project_id}/api-keys", headers=headers_a)
    assert listed.status_code == 200
    assert "key" not in listed.json()[0]
    assert raw_key not in listed.text
    async with session_factory() as session:
        stored = await session.scalar(select(ApiKey))
        assert stored is not None
        assert stored.key_hash != raw_key

    token_b, _ = await register_user(client, "b@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    foreign_project = await client.get(f"/api/v1/projects/{project_id}", headers=headers_b)
    assert foreign_project.status_code == 404
    foreign_keys = await client.get(f"/api/v1/projects/{project_id}/api-keys", headers=headers_b)
    assert foreign_keys.status_code == 404
