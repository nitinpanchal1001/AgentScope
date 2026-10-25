from decimal import Decimal

from conftest import register_user
from httpx import AsyncClient
from pytest import MonkeyPatch


async def _workspace(client: AsyncClient, email: str) -> tuple[dict[str, str], str, str]:
    token, _ = await register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": f"Experiment {email}"}, headers=headers
    )
    project = await client.post(
        f"/api/v1/organizations/{organization.json()['id']}/projects",
        json={"name": "Experiment Agent"},
        headers=headers,
    )
    project_id = project.json()["id"]
    environments = await client.get(f"/api/v1/projects/{project_id}/environments", headers=headers)
    environment_id = next(
        item["id"] for item in environments.json() if item["slug"] == "development"
    )
    return headers, project_id, environment_id


async def _dataset(
    client: AsyncClient,
    headers: dict[str, str],
    project_id: str,
    count: int = 1,
) -> str:
    response = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=headers,
        json={
            "name": f"Golden Cases {count}",
            "items": [
                {
                    "input": {"question": f"Question {index}"},
                    "expected_output": f"Answer {index}",
                }
                for index in range(1, count + 1)
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["latest_version"]["id"]


async def _evaluator(client: AsyncClient, headers: dict[str, str], project_id: str) -> str:
    response = await client.post(
        f"/api/v1/projects/{project_id}/evaluators",
        headers=headers,
        json={
            "name": "Golden exact match",
            "version": {
                "type": "EXACT_MATCH",
                "configuration": {},
                "threshold": "1",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["versions"][0]["id"]


async def test_experiment_executes_fixed_dataset_and_aggregates_results(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(
        "agentscope_api.api.routers.experiments.dispatch_experiment_run",
        lambda run_id: not dispatched.append(str(run_id)),
    )
    headers, project_id, environment_id = await _workspace(client, "experiment-engine@example.com")
    dataset_version_id = await _dataset(client, headers, project_id)
    evaluator_version_id = await _evaluator(client, headers, project_id)
    created = await client.post(
        f"/api/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "Support agent v2",
            "dataset_version_id": dataset_version_id,
            "environment_id": environment_id,
            "agent": {
                "type": "http",
                "endpoint": "https://agent.example.com/invoke",
                "provider": "test",
                "model": "deterministic-agent",
                "prompt_version": "support-v2",
            },
            "evaluator_version_ids": [evaluator_version_id],
            "max_concurrency": 1,
        },
    )
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"
    assert created.json()["dataset_version_id"] == dataset_version_id

    started = await client.post(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/start",
        headers=headers,
    )
    assert started.status_code == 202, started.text
    assert started.json()["status"] == "RUNNING"
    assert len(dispatched) == 1

    runs = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/runs",
        headers=headers,
    )
    run_id = runs.json()["items"][0]["id"]
    worker_headers = {"X-AgentScope-Worker-Key": "development-only-worker-key-change-me"}
    payload = await client.get(
        f"/internal/v1/experiment-runs/{run_id}/payload", headers=worker_headers
    )
    assert payload.status_code == 200, payload.text
    assert payload.json()["request"]["input"] == {"question": "Question 1"}
    assert payload.json()["request"]["metadata"]["experiment_id"] == experiment_id

    invocation = await client.post(
        f"/internal/v1/experiment-runs/{run_id}/complete",
        headers=worker_headers,
        json={
            "status": "SUCCESS",
            "output": "Answer 1",
            "metadata": {"agent": "fixture"},
            "latency_ms": 25,
            "input_tokens": 5,
            "output_tokens": 3,
            "total_tokens": 8,
            "total_cost": "0.0008",
        },
    )
    assert invocation.status_code == 200, invocation.text
    assert len(invocation.json()["evaluation_result_ids"]) == 1
    result_id = invocation.json()["evaluation_result_ids"][0]

    evaluation_payload = await client.get(
        f"/internal/v1/evaluation-results/{result_id}/payload", headers=worker_headers
    )
    assert evaluation_payload.status_code == 200, evaluation_payload.text
    assert evaluation_payload.json()["expected_output"] == "Answer 1"
    completed = await client.post(
        f"/internal/v1/evaluation-results/{result_id}/complete",
        headers=worker_headers,
        json={
            "status": "SUCCESS",
            "score": "1",
            "passed": True,
            "label": "PASS",
            "reason": "Exact match",
        },
    )
    assert completed.status_code == 204, completed.text

    final = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}", headers=headers
    )
    assert final.json()["status"] == "COMPLETED"
    assert final.json()["completed_cases"] == 1
    assert final.json()["passed_cases"] == 1
    assert final.json()["metrics"]["pass_rate"] == 1
    assert Decimal(final.json()["metrics"]["total_cost"]) == Decimal("0.0008")
    final_runs = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/runs",
        headers=headers,
    )
    assert final_runs.json()["items"][0]["status"] == "COMPLETED"
    assert final_runs.json()["items"][0]["trace_id"] is not None

    foreign_headers, foreign_project_id, _ = await _workspace(
        client, "foreign-experiment@example.com"
    )
    hidden = await client.get(
        f"/api/v1/projects/{foreign_project_id}/experiments/{experiment_id}",
        headers=foreign_headers,
    )
    assert hidden.status_code == 404


async def test_experiment_scheduler_respects_concurrency_and_claims_next_case(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(
        "agentscope_api.api.routers.experiments.dispatch_experiment_run",
        lambda run_id: not dispatched.append(str(run_id)),
    )
    headers, project_id, environment_id = await _workspace(
        client, "experiment-concurrency@example.com"
    )
    dataset_version_id = await _dataset(client, headers, project_id, count=3)
    evaluator_version_id = await _evaluator(client, headers, project_id)
    created = await client.post(
        f"/api/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "Controlled concurrency",
            "dataset_version_id": dataset_version_id,
            "environment_id": environment_id,
            "agent": {"endpoint": "https://agent.example.com/invoke"},
            "evaluator_version_ids": [evaluator_version_id],
            "max_concurrency": 2,
        },
    )
    experiment_id = created.json()["id"]
    await client.post(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/start",
        headers=headers,
    )
    assert len(dispatched) == 2
    runs = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/runs",
        headers=headers,
    )
    statuses = [item["status"] for item in runs.json()["items"]]
    assert statuses == ["RUNNING", "RUNNING", "PENDING"]

    failed = await client.post(
        f"/internal/v1/experiment-runs/{runs.json()['items'][0]['id']}/complete",
        headers={"X-AgentScope-Worker-Key": "development-only-worker-key-change-me"},
        json={
            "status": "FAILED",
            "error_type": "AgentTimeout",
            "error_message": "Timed out",
            "latency_ms": 1000,
        },
    )
    assert failed.status_code == 200, failed.text
    assert len(failed.json()["next_run_ids"]) == 1
    refreshed = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/runs",
        headers=headers,
    )
    assert [item["status"] for item in refreshed.json()["items"]] == [
        "FAILED",
        "RUNNING",
        "RUNNING",
    ]
