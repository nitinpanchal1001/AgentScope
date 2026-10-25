from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from conftest import register_user
from httpx import AsyncClient

from agentscope_api.services.pricing import calculate_cost


def test_cost_calculator_uses_decimal_per_million_rates() -> None:
    assert calculate_cost(
        input_tokens=1_000,
        output_tokens=500,
        input_price_per_million_tokens=Decimal("1"),
        output_price_per_million_tokens=Decimal("2"),
    ) == Decimal("0.002000000000")


async def _workspace(client: AsyncClient, email: str) -> tuple[dict[str, str], str, str, str]:
    token, _ = await register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": f"Metrics {email}"}, headers=headers
    )
    project = await client.post(
        f"/api/v1/organizations/{organization.json()['id']}/projects",
        json={"name": "Metrics Agent"},
        headers=headers,
    )
    project_id = project.json()["id"]
    environments = await client.get(f"/api/v1/projects/{project_id}/environments", headers=headers)
    development = next(item for item in environments.json() if item["slug"] == "development")
    key = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        json={"name": "Metrics SDK", "environment_id": development["id"]},
        headers=headers,
    )
    return headers, project_id, development["id"], key.json()["key"]


async def test_pricing_rollup_and_tenant_scoped_analytics(client: AsyncClient) -> None:
    headers, project_id, environment_id, api_key = await _workspace(client, "metrics@example.com")
    now = datetime.now(UTC)
    pricing = await client.post(
        f"/api/v1/projects/{project_id}/model-pricing",
        headers=headers,
        json={
            "provider": "Test Provider",
            "model": "Test Model",
            "input_price_per_million_tokens": "1",
            "output_price_per_million_tokens": "2",
            "effective_from": (now - timedelta(hours=1)).isoformat(),
        },
    )
    assert pricing.status_code == 201, pricing.text
    assert pricing.json()["custom"] is True
    next_start = now + timedelta(hours=1)
    next_pricing = await client.post(
        f"/api/v1/projects/{project_id}/model-pricing",
        headers=headers,
        json={
            "provider": "Test Provider",
            "model": "Test Model",
            "input_price_per_million_tokens": "3",
            "output_price_per_million_tokens": "4",
            "effective_from": next_start.isoformat(),
        },
    )
    assert next_pricing.status_code == 201, next_pricing.text
    pricing_versions = await client.get(
        f"/api/v1/projects/{project_id}/model-pricing", headers=headers
    )
    first_version = next(
        item for item in pricing_versions.json() if item["id"] == pricing.json()["id"]
    )
    closed_at = datetime.fromisoformat(first_version["effective_to"])
    if closed_at.tzinfo is None:
        closed_at = closed_at.replace(tzinfo=UTC)
    assert closed_at == next_start

    trace_id = str(uuid4())
    span_id = str(uuid4())
    events = [
        {
            "event_id": str(uuid4()),
            "timestamp": now.isoformat(),
            "type": "TRACE_START",
            "trace_id": trace_id,
            "payload": {"name": "metrics-agent", "agent_version": "v3"},
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=5)).isoformat(),
            "type": "SPAN_START",
            "trace_id": trace_id,
            "span_id": span_id,
            "payload": {
                "name": "generate-answer",
                "span_type": "LLM",
                "provider": "Test Provider",
                "model": "Test Model",
            },
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=25)).isoformat(),
            "type": "SPAN_END",
            "trace_id": trace_id,
            "span_id": span_id,
            "payload": {
                "status": "SUCCESS",
                "input_tokens": 1000,
                "output_tokens": 500,
                "total_tokens": 1500,
                "output": {"answer": "done"},
            },
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=40)).isoformat(),
            "type": "TRACE_END",
            "trace_id": trace_id,
            "payload": {"status": "SUCCESS", "output": {"answer": "done"}},
        },
    ]
    ingest = await client.post(
        "/v1/ingest/batch",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"sdk": {"name": "agentscope-python", "version": "0.3.0"}, "events": events},
    )
    assert ingest.status_code == 202, ingest.text

    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    summary = traces.json()["items"][0]
    assert summary["total_tokens"] == 1500
    assert Decimal(summary["total_cost"]) == Decimal("0.002000000000")

    detail = await client.get(f"/api/v1/traces/{summary['id']}", headers=headers)
    assert detail.json()["spans"][0]["pricing_id"] == pricing.json()["id"]

    analytics = await client.get(
        f"/api/v1/projects/{project_id}/analytics",
        params={"environment_id": environment_id, "bucket": "1h"},
        headers=headers,
    )
    assert analytics.status_code == 200, analytics.text
    payload = analytics.json()
    assert payload["summary"]["total_traces"] == 1
    assert payload["summary"]["success_rate"] == 100.0
    assert payload["summary"]["total_tokens"] == 1500
    assert Decimal(payload["summary"]["total_cost"]) == Decimal("0.002000000000")
    assert payload["models"][0]["name"] == "Test Model"
    assert payload["providers"][0]["name"] == "Test Provider"

    foreign_headers, _, _, _ = await _workspace(client, "foreign-metrics@example.com")
    denied = await client.get(f"/api/v1/projects/{project_id}/analytics", headers=foreign_headers)
    assert denied.status_code == 404


async def test_analytics_rejects_unbounded_range(client: AsyncClient) -> None:
    headers, project_id, _, _ = await _workspace(client, "range@example.com")
    now = datetime.now(UTC)
    response = await client.get(
        f"/api/v1/projects/{project_id}/analytics",
        params={
            "started_after": (now - timedelta(days=91)).isoformat(),
            "started_before": now.isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ANALYTICS_RANGE_TOO_LARGE"
