from datetime import UTC, datetime, timedelta
from uuid import uuid4

from conftest import register_user
from httpx import AsyncClient


async def _workspace(client: AsyncClient, email: str) -> tuple[dict[str, str], str, str, str]:
    token, _ = await register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": f"Isolation {email}"}, headers=headers
    )
    project = await client.post(
        f"/api/v1/organizations/{organization.json()['id']}/projects",
        json={"name": "Isolated Agent"},
        headers=headers,
    )
    project_id = project.json()["id"]
    environments = await client.get(f"/api/v1/projects/{project_id}/environments", headers=headers)
    environment_id = next(
        item["id"] for item in environments.json() if item["slug"] == "development"
    )
    key = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        json={"name": "Isolation SDK", "environment_id": environment_id},
        headers=headers,
    )
    return headers, project_id, environment_id, key.json()["key"]


async def test_direct_uuid_access_never_crosses_tenants(client: AsyncClient) -> None:
    owner, project_id, environment_id, api_key = await _workspace(
        client, "tenant-owner@example.com"
    )
    foreign, foreign_project_id, _, _ = await _workspace(client, "tenant-foreign@example.com")

    dataset = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=owner,
        json={
            "name": "Private golden set",
            "items": [{"input": "private question", "expected_output": "private answer"}],
        },
    )
    dataset_id = dataset.json()["id"]
    dataset_version_id = dataset.json()["latest_version"]["id"]
    evaluator = await client.post(
        f"/api/v1/projects/{project_id}/evaluators",
        headers=owner,
        json={
            "name": "Private exact match",
            "version": {"type": "EXACT_MATCH", "configuration": {}, "threshold": "1"},
        },
    )
    evaluator_version_id = evaluator.json()["versions"][0]["id"]
    experiment = await client.post(
        f"/api/v1/projects/{project_id}/experiments",
        headers=owner,
        json={
            "name": "Private experiment",
            "dataset_version_id": dataset_version_id,
            "environment_id": environment_id,
            "agent": {"endpoint": "https://agent.example.com/invoke"},
            "evaluator_version_ids": [evaluator_version_id],
        },
    )
    experiment_id = experiment.json()["id"]

    now = datetime.now(UTC)
    external_id = str(uuid4())
    ingested = await client.post(
        "/v1/ingest/batch",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "sdk": {"name": "tenant-suite", "version": "1"},
            "events": [
                {
                    "event_id": str(uuid4()),
                    "timestamp": now.isoformat(),
                    "type": "TRACE_START",
                    "trace_id": external_id,
                    "payload": {"name": "private-trace", "input": "secret"},
                },
                {
                    "event_id": str(uuid4()),
                    "timestamp": (now + timedelta(milliseconds=1)).isoformat(),
                    "type": "TRACE_END",
                    "trace_id": external_id,
                    "payload": {"status": "SUCCESS", "output": "secret-result"},
                },
            ],
        },
    )
    assert ingested.status_code == 202, ingested.text
    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=owner)
    trace_id = traces.json()["items"][0]["id"]

    attempts = [
        await client.get(f"/api/v1/projects/{project_id}", headers=foreign),
        await client.get(f"/api/v1/projects/{project_id}/api-keys", headers=foreign),
        await client.get(f"/api/v1/traces/{trace_id}", headers=foreign),
        await client.get(
            f"/api/v1/projects/{foreign_project_id}/datasets/{dataset_id}", headers=foreign
        ),
        await client.get(
            f"/api/v1/projects/{foreign_project_id}/experiments/{experiment_id}",
            headers=foreign,
        ),
    ]
    assert [response.status_code for response in attempts] == [404, 404, 404, 404, 404]
    assert all("secret" not in response.text for response in attempts)
