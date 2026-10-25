from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from conftest import register_user
from httpx import AsyncClient
from pytest import MonkeyPatch


async def _workspace(client: AsyncClient, email: str) -> tuple[dict[str, str], str, str, str]:
    token, _ = await register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": f"Evaluation {email}"}, headers=headers
    )
    project = await client.post(
        f"/api/v1/organizations/{organization.json()['id']}/projects",
        json={"name": "Evaluation Agent"},
        headers=headers,
    )
    project_id = project.json()["id"]
    environments = await client.get(f"/api/v1/projects/{project_id}/environments", headers=headers)
    development = next(item for item in environments.json() if item["slug"] == "development")
    key = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        json={"name": "Evaluation SDK", "environment_id": development["id"]},
        headers=headers,
    )
    return headers, project_id, development["id"], key.json()["key"]


async def test_versioned_evaluator_production_binding_and_worker_completion(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(
        "agentscope_api.api.routers.ingestion.dispatch_evaluation",
        lambda result_id: dispatched.append(str(result_id)),
    )
    headers, project_id, environment_id, api_key = await _workspace(
        client, "evaluation@example.com"
    )
    evaluator = await client.post(
        f"/api/v1/projects/{project_id}/evaluators",
        headers=headers,
        json={
            "name": "Contains resolution",
            "description": "The answer must explain the resolution.",
            "version": {
                "type": "CONTAINS",
                "configuration": {"value": "resolved"},
                "threshold": "1",
            },
        },
    )
    assert evaluator.status_code == 201, evaluator.text
    evaluator_id = evaluator.json()["id"]
    first_version = evaluator.json()["versions"][0]

    version = await client.post(
        f"/api/v1/projects/{project_id}/evaluators/{evaluator_id}/versions",
        headers=headers,
        json={
            "type": "CONTAINS",
            "configuration": {"value": "successfully resolved"},
            "threshold": "1",
        },
    )
    assert version.status_code == 201, version.text
    assert version.json()["version"] == 2
    listed = await client.get(f"/api/v1/projects/{project_id}/evaluators", headers=headers)
    assert [item["version"] for item in listed.json()[0]["versions"]] == [2, 1]
    assert listed.json()[0]["versions"][1]["configuration"] == {"value": "resolved"}

    binding = await client.post(
        f"/api/v1/projects/{project_id}/evaluation-bindings",
        headers=headers,
        json={
            "environment_id": environment_id,
            "evaluator_version_id": first_version["id"],
            "sample_rate": "1",
            "threshold": "0.7",
            "filters": {"statuses": ["SUCCESS"], "tags_any": ["support"]},
        },
    )
    assert binding.status_code == 201, binding.text

    now = datetime.now(UTC)
    external_trace_id = str(uuid4())
    ingest = await client.post(
        "/v1/ingest/batch",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "sdk": {"name": "agentscope-python", "version": "0.4.0"},
            "events": [
                {
                    "event_id": str(uuid4()),
                    "timestamp": now.isoformat(),
                    "type": "TRACE_START",
                    "trace_id": external_trace_id,
                    "payload": {
                        "name": "support-agent",
                        "input": {"question": "Can you help?"},
                        "tags": ["support"],
                    },
                },
                {
                    "event_id": str(uuid4()),
                    "timestamp": (now + timedelta(milliseconds=20)).isoformat(),
                    "type": "TRACE_END",
                    "trace_id": external_trace_id,
                    "payload": {
                        "status": "SUCCESS",
                        "output": "Your request was resolved.",
                    },
                },
            ],
        },
    )
    assert ingest.status_code == 202, ingest.text
    assert len(dispatched) == 1

    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    trace_id = traces.json()["items"][0]["id"]
    results = await client.get(
        f"/api/v1/projects/{project_id}/traces/{trace_id}/evaluations", headers=headers
    )
    assert results.status_code == 200
    assert results.json()[0]["status"] == "PENDING"
    assert results.json()[0]["source"] == "PRODUCTION"
    result_id = results.json()[0]["id"]

    denied = await client.get(f"/internal/v1/evaluation-results/{result_id}/payload")
    assert denied.status_code == 401
    worker_headers = {"X-AgentScope-Worker-Key": "development-only-worker-key-change-me"}
    worker_payload = await client.get(
        f"/internal/v1/evaluation-results/{result_id}/payload", headers=worker_headers
    )
    assert worker_payload.status_code == 200, worker_payload.text
    assert worker_payload.json()["status"] == "RUNNING"
    assert Decimal(worker_payload.json()["threshold"]) == Decimal("0.7")
    assert worker_payload.json()["trace"]["tags"] == ["support"]

    completed = await client.post(
        f"/internal/v1/evaluation-results/{result_id}/complete",
        headers=worker_headers,
        json={
            "status": "SUCCESS",
            "score": "1",
            "passed": True,
            "label": "PASS",
            "reason": "Candidate contains the configured value",
            "evidence": [{"value": "resolved"}],
            "metadata": {"engine": "deterministic"},
        },
    )
    assert completed.status_code == 204, completed.text
    final_results = await client.get(
        f"/api/v1/projects/{project_id}/traces/{trace_id}/evaluations", headers=headers
    )
    assert final_results.json()[0]["status"] == "SUCCESS"
    assert Decimal(final_results.json()[0]["score"]) == Decimal("1")
    updated_traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    assert Decimal(updated_traces.json()["items"][0]["evaluation_score"]) == Decimal("1")

    foreign_headers, foreign_project_id, _, _ = await _workspace(
        client, "foreign-evaluation@example.com"
    )
    foreign = await client.get(
        f"/api/v1/projects/{foreign_project_id}/traces/{trace_id}/evaluations",
        headers=foreign_headers,
    )
    assert foreign.status_code == 200
    assert foreign.json() == []


async def test_llm_evaluator_requires_a_complete_judge_configuration(
    client: AsyncClient,
) -> None:
    headers, project_id, _, _ = await _workspace(client, "judge-validation@example.com")
    response = await client.post(
        f"/api/v1/projects/{project_id}/evaluators",
        headers=headers,
        json={
            "name": "Correctness judge",
            "version": {"type": "CORRECTNESS", "provider": "openai"},
        },
    )
    assert response.status_code == 422
