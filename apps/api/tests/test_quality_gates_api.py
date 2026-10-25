from httpx import AsyncClient
from pytest import MonkeyPatch
from test_experiments_api import _dataset, _evaluator, _workspace

WORKER_HEADERS = {"X-AgentScope-Worker-Key": "development-only-worker-key-change-me"}


async def _completed_experiment(
    client: AsyncClient,
    headers: dict[str, str],
    project_id: str,
    environment_id: str,
    dataset_version_id: str,
    evaluator_version_id: str,
    *,
    name: str,
    passed: bool,
    latency_ms: int,
    cost: str,
) -> str:
    created = await client.post(
        f"/api/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": name,
            "dataset_version_id": dataset_version_id,
            "environment_id": environment_id,
            "agent": {"endpoint": "https://agent.example.com/invoke"},
            "evaluator_version_ids": [evaluator_version_id],
            "max_concurrency": 1,
        },
    )
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]
    started = await client.post(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/start",
        headers=headers,
    )
    assert started.status_code == 202, started.text
    runs = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{experiment_id}/runs",
        headers=headers,
    )
    run_id = runs.json()["items"][0]["id"]
    invocation = await client.post(
        f"/internal/v1/experiment-runs/{run_id}/complete",
        headers=WORKER_HEADERS,
        json={
            "status": "SUCCESS",
            "output": "Answer 1" if passed else "Wrong answer",
            "latency_ms": latency_ms,
            "input_tokens": 5,
            "output_tokens": 3,
            "total_tokens": 8,
            "total_cost": cost,
        },
    )
    assert invocation.status_code == 200, invocation.text
    result_id = invocation.json()["evaluation_result_ids"][0]
    evaluation = await client.post(
        f"/internal/v1/evaluation-results/{result_id}/complete",
        headers=WORKER_HEADERS,
        json={
            "status": "SUCCESS",
            "score": "1" if passed else "0",
            "passed": passed,
            "label": "PASS" if passed else "FAIL",
            "reason": "Quality gate fixture",
        },
    )
    assert evaluation.status_code == 204, evaluation.text
    return experiment_id


async def test_quality_gate_persists_baseline_comparison_and_failure(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agentscope_api.api.routers.experiments.dispatch_experiment_run",
        lambda run_id: True,
    )
    headers, project_id, environment_id = await _workspace(client, "quality-gates@example.com")
    dataset_version_id = await _dataset(client, headers, project_id)
    evaluator_version_id = await _evaluator(client, headers, project_id)
    baseline_id = await _completed_experiment(
        client,
        headers,
        project_id,
        environment_id,
        dataset_version_id,
        evaluator_version_id,
        name="Stable production agent",
        passed=True,
        latency_ms=100,
        cost="0.001",
    )
    candidate_id = await _completed_experiment(
        client,
        headers,
        project_id,
        environment_id,
        dataset_version_id,
        evaluator_version_id,
        name="Regressing candidate",
        passed=False,
        latency_ms=150,
        cost="0.002",
    )

    baseline = await client.post(
        f"/api/v1/projects/{project_id}/experiments/{baseline_id}/baseline",
        headers=headers,
    )
    assert baseline.status_code == 200, baseline.text
    dataset_id = baseline.json()["dataset_id"]
    fetched_baseline = await client.get(
        f"/api/v1/projects/{project_id}/baseline",
        params={"dataset_id": dataset_id},
        headers=headers,
    )
    assert fetched_baseline.json()["experiment_id"] == baseline_id

    comparison = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{candidate_id}/comparison",
        headers=headers,
    )
    assert comparison.status_code == 200, comparison.text
    metrics = {item["metric"]: item for item in comparison.json()}
    assert metrics["pass_rate"]["classification"] == "REGRESSION"
    assert metrics["p95_latency_ms"]["percentage_delta"] == 0.5
    assert metrics["total_cost"]["direction"] == "UP"

    gate = await client.post(
        f"/api/v1/projects/{project_id}/quality-gates",
        headers=headers,
        json={
            "name": "Production release",
            "description": "Reject correctness regressions and report latency growth.",
            "rules": [
                {
                    "metric": "pass_rate",
                    "constraint": "max_regression",
                    "threshold": 0.03,
                    "comparison": "absolute",
                    "severity": "FAIL",
                },
                {
                    "metric": "p95_latency_ms",
                    "constraint": "max_increase",
                    "threshold": 0.25,
                    "comparison": "relative",
                    "severity": "WARN",
                },
            ],
        },
    )
    assert gate.status_code == 201, gate.text
    evaluated = await client.post(
        f"/api/v1/projects/{project_id}/quality-gates/{gate.json()['id']}/evaluate",
        headers=headers,
        json={"candidate_experiment_id": candidate_id},
    )
    assert evaluated.status_code == 201, evaluated.text
    assert evaluated.json()["status"] == "FAILED"
    assert evaluated.json()["violations"][0]["metric"] == "pass_rate"
    assert evaluated.json()["warnings"][0]["metric"] == "p95_latency_ms"

    history = await client.get(
        f"/api/v1/projects/{project_id}/experiments/{candidate_id}/quality-gate-results",
        headers=headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["id"] == evaluated.json()["id"]

    foreign_headers, foreign_project_id, _ = await _workspace(
        client, "foreign-quality-gates@example.com"
    )
    hidden = await client.get(
        f"/api/v1/projects/{foreign_project_id}/experiments/{candidate_id}/comparison",
        headers=foreign_headers,
    )
    assert hidden.status_code == 404


async def test_quality_gate_returns_warning_only_and_rejects_zero_relative_baseline(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agentscope_api.api.routers.experiments.dispatch_experiment_run",
        lambda run_id: True,
    )
    headers, project_id, environment_id = await _workspace(
        client, "quality-gate-warning@example.com"
    )
    dataset_version_id = await _dataset(client, headers, project_id)
    evaluator_version_id = await _evaluator(client, headers, project_id)
    baseline_id = await _completed_experiment(
        client,
        headers,
        project_id,
        environment_id,
        dataset_version_id,
        evaluator_version_id,
        name="Zero-cost baseline",
        passed=True,
        latency_ms=100,
        cost="0",
    )
    candidate_id = await _completed_experiment(
        client,
        headers,
        project_id,
        environment_id,
        dataset_version_id,
        evaluator_version_id,
        name="Slow candidate",
        passed=True,
        latency_ms=130,
        cost="0.001",
    )
    await client.post(
        f"/api/v1/projects/{project_id}/experiments/{baseline_id}/baseline",
        headers=headers,
    )
    warning_gate = await client.post(
        f"/api/v1/projects/{project_id}/quality-gates",
        headers=headers,
        json={
            "name": "Latency warning",
            "rules": [
                {
                    "metric": "p95_latency_ms",
                    "constraint": "max_increase",
                    "threshold": 0.25,
                    "comparison": "relative",
                    "severity": "WARN",
                }
            ],
        },
    )
    warned = await client.post(
        f"/api/v1/projects/{project_id}/quality-gates/{warning_gate.json()['id']}/evaluate",
        headers=headers,
        json={"candidate_experiment_id": candidate_id},
    )
    assert warned.status_code == 201, warned.text
    assert warned.json()["status"] == "PASSED_WITH_WARNINGS"

    invalid_gate = await client.post(
        f"/api/v1/projects/{project_id}/quality-gates",
        headers=headers,
        json={
            "name": "Relative zero-cost rule",
            "rules": [
                {
                    "metric": "average_cost",
                    "constraint": "max_increase",
                    "threshold": 0.15,
                    "comparison": "relative",
                    "severity": "WARN",
                }
            ],
        },
    )
    rejected = await client.post(
        f"/api/v1/projects/{project_id}/quality-gates/{invalid_gate.json()['id']}/evaluate",
        headers=headers,
        json={"candidate_experiment_id": candidate_id},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "UNDEFINED_RELATIVE_COMPARISON"
