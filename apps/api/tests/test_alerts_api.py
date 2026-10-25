from datetime import UTC, datetime, timedelta
from uuid import UUID

from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_failure_intelligence_api import _failed_trace
from test_tracing_api import _workspace

from agentscope_api.models import Trace
from agentscope_api.services.failure_intelligence import QdrantFailureIndex

WORKER_HEADERS = {"X-AgentScope-Worker-Key": "development-only-worker-key-change-me"}


async def test_alert_rule_evaluation_cooldown_delivery_and_tenant_isolation(
    client: AsyncClient,
) -> None:
    headers, project_id, api_key = await _workspace(client, "alerts@example.com")
    await _failed_trace(client, project_id, api_key)
    created = await client.post(
        f"/api/v1/projects/{project_id}/alert-rules",
        headers=headers,
        json={
            "name": "Production errors",
            "metric": "ERROR_RATE",
            "operator": "GREATER_THAN",
            "threshold": "10",
            "window_minutes": 60,
            "severity": "CRITICAL",
            "enabled": True,
            "channel": "WEBHOOK",
            "channel_target": "https://example.com/alerts?token=secret",
            "cooldown_minutes": 30,
        },
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["channel_target"] == "https://example.com/alerts"

    rejected = await client.post("/internal/v1/alerts/evaluate")
    assert rejected.status_code == 401
    evaluated = await client.post("/internal/v1/alerts/evaluate", headers=WORKER_HEADERS)
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["evaluated_rules"] == 1
    assert len(evaluated.json()["triggered"]) == 1
    event = evaluated.json()["triggered"][0]
    assert float(event["observed_value"]) == 100
    assert event["channel_target"].endswith("token=secret")

    duplicate = await client.post("/internal/v1/alerts/evaluate", headers=WORKER_HEADERS)
    assert duplicate.json()["triggered"] == []
    delivered = await client.post(
        f"/internal/v1/alerts/{event['id']}/delivery",
        headers=WORKER_HEADERS,
        json={"delivered": True},
    )
    assert delivered.json()["status"] == "DELIVERED"
    history = await client.get(f"/api/v1/projects/{project_id}/alerts", headers=headers)
    assert history.json()[0]["delivery_attempts"] == 1

    foreign_headers, foreign_project_id, _ = await _workspace(client, "foreign-alerts@example.com")
    hidden = await client.put(
        f"/api/v1/projects/{foreign_project_id}/alert-rules/{rule['id']}",
        headers=foreign_headers,
        json={
            "name": "Hidden",
            "metric": "ERROR_RATE",
            "operator": "GREATER_THAN",
            "threshold": "1",
            "channel": "EMAIL",
            "channel_target": "owner@example.com",
        },
    )
    assert hidden.status_code == 404


async def test_retention_update_and_hard_delete(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: MonkeyPatch,
) -> None:
    async def no_delete(self: QdrantFailureIndex, point_ids: object) -> None:
        return None

    monkeypatch.setattr(QdrantFailureIndex, "delete_points", no_delete)
    headers, project_id, api_key = await _workspace(client, "retention@example.com")
    external_id = await _failed_trace(client, project_id, api_key)
    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    trace_id = next(
        item["id"] for item in traces.json()["items"] if item["external_trace_id"] == external_id
    )
    updated = await client.patch(
        f"/api/v1/projects/{project_id}/retention",
        headers=headers,
        json={"retention_days": 1},
    )
    assert updated.json()["retention_days"] == 1
    async with session_factory() as session:
        await session.execute(
            update(Trace)
            .where(Trace.id == UUID(trace_id))
            .values(created_at=datetime.now(UTC) - timedelta(days=2))
        )
        await session.commit()

    expired = await client.post("/internal/v1/maintenance/retention", headers=WORKER_HEADERS)
    assert expired.status_code == 200, expired.text
    assert expired.json()["deleted_traces"] == 1
    remaining = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    assert remaining.json()["items"] == []
