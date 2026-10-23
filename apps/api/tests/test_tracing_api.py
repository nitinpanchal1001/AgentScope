from datetime import UTC, datetime, timedelta
from uuid import uuid4

from conftest import register_user
from httpx import AsyncClient


async def _workspace(client: AsyncClient, email: str) -> tuple[dict[str, str], str, str]:
    token, _ = await register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": "Tracing Org"}, headers=headers
    )
    project = await client.post(
        f"/api/v1/organizations/{organization.json()['id']}/projects",
        json={"name": "Support Agent"},
        headers=headers,
    )
    project_id = project.json()["id"]
    environments = await client.get(f"/api/v1/projects/{project_id}/environments", headers=headers)
    development = next(item for item in environments.json() if item["slug"] == "development")
    key = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        json={"name": "SDK", "environment_id": development["id"]},
        headers=headers,
    )
    return headers, project_id, key.json()["key"]


async def test_idempotent_ingestion_and_tenant_scoped_trace_explorer(
    client: AsyncClient,
) -> None:
    headers, project_id, api_key = await _workspace(client, "tracer@example.com")
    now = datetime.now(UTC)
    trace_external_id = str(uuid4())
    span_external_id = str(uuid4())
    events = [
        {
            "event_id": str(uuid4()),
            "timestamp": now.isoformat(),
            "type": "TRACE_START",
            "trace_id": trace_external_id,
            "payload": {
                "name": "support-agent",
                "input": {"message": "Where is my order?"},
                "agent_version": "v2",
                "tags": ["support"],
            },
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=5)).isoformat(),
            "type": "SPAN_START",
            "trace_id": trace_external_id,
            "span_id": span_external_id,
            "payload": {
                "name": "lookup-order",
                "span_type": "TOOL",
                "input": {"order_id": "A-42"},
            },
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=25)).isoformat(),
            "type": "SPAN_END",
            "trace_id": trace_external_id,
            "span_id": span_external_id,
            "payload": {"status": "SUCCESS", "output": {"state": "shipped"}},
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=40)).isoformat(),
            "type": "TRACE_END",
            "trace_id": trace_external_id,
            "payload": {
                "status": "SUCCESS",
                "output": {"answer": "Your order shipped."},
                "input_tokens": 10,
                "output_tokens": 7,
                "total_tokens": 17,
            },
        },
    ]
    batch = {"sdk": {"name": "agentscope-python", "version": "0.2.0"}, "events": events}
    ingest_headers = {"Authorization": f"Bearer {api_key}"}

    first = await client.post("/v1/ingest/batch", json=batch, headers=ingest_headers)
    assert first.status_code == 202, first.text
    assert first.json() == {"accepted": 4, "duplicates": 0}
    repeated = await client.post("/v1/ingest/batch", json=batch, headers=ingest_headers)
    assert repeated.status_code == 202
    assert repeated.json() == {"accepted": 0, "duplicates": 4}

    page = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 1
    summary = page.json()["items"][0]
    assert summary["status"] == "SUCCESS"
    assert summary["environment"] == "development"
    assert summary["total_tokens"] == 17
    tagged = await client.get(f"/api/v1/projects/{project_id}/traces?tag=support", headers=headers)
    assert len(tagged.json()["items"]) == 1
    missing_tag = await client.get(
        f"/api/v1/projects/{project_id}/traces?tag=missing", headers=headers
    )
    assert missing_tag.json()["items"] == []

    detail = await client.get(f"/api/v1/traces/{summary['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["input"] == {"message": "Where is my order?"}
    assert detail.json()["spans"][0]["name"] == "lookup-order"
    assert detail.json()["spans"][0]["status"] == "SUCCESS"

    foreign_headers, _, _ = await _workspace(client, "other-tracer@example.com")
    denied = await client.get(f"/api/v1/traces/{summary['id']}", headers=foreign_headers)
    assert denied.status_code == 404


async def test_ingestion_rejects_invalid_project_key(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/ingest/batch",
        headers={"Authorization": "Bearer as_test_not-a-real-key"},
        json={"sdk": {"name": "agentscope-python", "version": "0.2.0"}, "events": []},
    )
    assert response.status_code == 401
