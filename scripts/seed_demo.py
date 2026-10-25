"""Seed a runnable customer-support comparison through AgentScope's public API."""

import json
import os
from pathlib import Path
from typing import Any

import httpx

API_URL = os.getenv("AGENTSCOPE_API_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.getenv("AGENTSCOPE_DEMO_EMAIL", "demo@agentscope.dev")
PASSWORD = os.getenv("AGENTSCOPE_DEMO_PASSWORD", "agentscope-demo-2026-change-me")
AGENT_URL = os.getenv("AGENTSCOPE_DEMO_AGENT_URL", "http://demo-agent:8090/invoke")
DATASET_FILE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "customer-support-agent"
    / "golden_dataset.jsonl"
)


def checked(response: httpx.Response, *expected: int) -> Any:
    if response.status_code not in expected:
        raise RuntimeError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}: {response.text}"
        )
    return response.json() if response.content else None


def named(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in items if item["name"] == name), None)


def main() -> None:
    cases = [json.loads(line) for line in DATASET_FILE.read_text().splitlines() if line.strip()]
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        registration = client.post(
            "/api/v1/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "AgentScope Demo"},
        )
        if registration.status_code == 201:
            auth = registration.json()
        elif registration.status_code == 409:
            auth = checked(
                client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}),
                200,
            )
        else:
            checked(registration, 201)
            raise AssertionError("unreachable")
        client.headers["Authorization"] = f"Bearer {auth['access_token']}"

        organizations = checked(client.get("/api/v1/organizations"), 200)
        organization = named(organizations, "AgentScope Demo")
        if organization is None:
            organization = checked(
                client.post("/api/v1/organizations", json={"name": "AgentScope Demo"}), 201
            )

        projects = checked(
            client.get(f"/api/v1/organizations/{organization['id']}/projects"), 200
        )
        project = named(projects, "Customer Support Agent")
        if project is None:
            project = checked(
                client.post(
                    f"/api/v1/organizations/{organization['id']}/projects",
                    json={
                        "name": "Customer Support Agent",
                        "description": "Deterministic V1/V2 regression demonstration",
                    },
                ),
                201,
            )
        project_id = project["id"]
        environments = checked(client.get(f"/api/v1/projects/{project_id}/environments"), 200)
        environment = next(item for item in environments if item["slug"] == "development")

        keys = checked(client.get(f"/api/v1/projects/{project_id}/api-keys"), 200)
        if named(keys, "Demo SDK") is None:
            api_key = checked(
                client.post(
                    f"/api/v1/projects/{project_id}/api-keys",
                    json={"name": "Demo SDK", "environment_id": environment["id"]},
                ),
                201,
            )
            print(f"One-time demo SDK key: {api_key['key']}")

        datasets = checked(client.get(f"/api/v1/projects/{project_id}/datasets"), 200)
        dataset = named(datasets, "Customer Support Golden Cases")
        if dataset is None:
            dataset = checked(
                client.post(
                    f"/api/v1/projects/{project_id}/datasets",
                    json={
                        "name": "Customer Support Golden Cases",
                        "description": "Order, cancellation, refund, policy, and safety cases",
                        "metadata": {"source": "checked-in-demo", "schema_version": 1},
                        "items": cases,
                    },
                ),
                201,
            )
        else:
            version = client.post(
                f"/api/v1/projects/{project_id}/datasets/{dataset['id']}/versions",
                json={
                    "metadata": {"source": "checked-in-demo", "schema_version": 1},
                    "items": cases,
                },
            )
            if version.status_code not in {201, 409}:
                checked(version, 201)
            dataset = checked(
                client.get(f"/api/v1/projects/{project_id}/datasets/{dataset['id']}"), 200
            )

        evaluators = checked(client.get(f"/api/v1/projects/{project_id}/evaluators"), 200)
        evaluator = named(evaluators, "Exact expected response")
        if evaluator is None:
            evaluator = checked(
                client.post(
                    f"/api/v1/projects/{project_id}/evaluators",
                    json={
                        "name": "Exact expected response",
                        "description": "Deterministic response regression signal",
                        "version": {
                            "type": "EXACT_MATCH",
                            "configuration": {},
                            "threshold": "1",
                        },
                    },
                ),
                201,
            )
        evaluator_version_id = evaluator["versions"][0]["id"]

        experiments = checked(client.get(f"/api/v1/projects/{project_id}/experiments"), 200)
        created_or_existing: list[dict[str, Any]] = []
        for agent_version in ("support-v1", "support-v2"):
            experiment_name = f"Customer Support {agent_version.removeprefix('support-').upper()}"
            experiment = named(experiments, experiment_name)
            if experiment is None:
                experiment = checked(
                    client.post(
                        f"/api/v1/projects/{project_id}/experiments",
                        json={
                            "name": experiment_name,
                            "description": "Checked-in deterministic demonstration",
                            "dataset_version_id": dataset["latest_version"]["id"],
                            "environment_id": environment["id"],
                            "agent": {
                                "type": "http",
                                "endpoint": AGENT_URL,
                                "provider": "deterministic-demo",
                                "model": "customer-support-rules",
                                "prompt_version": agent_version,
                                "temperature": 0,
                            },
                            "evaluator_version_ids": [evaluator_version_id],
                            "max_concurrency": 4,
                        },
                    ),
                    201,
                )
            if experiment["status"] == "PENDING":
                experiment = checked(
                    client.post(
                        f"/api/v1/projects/{project_id}/experiments/{experiment['id']}/start"
                    ),
                    202,
                )
            created_or_existing.append(experiment)

    print(f"Demo user: {EMAIL}")
    print(f"Project ID: {project_id}")
    for experiment in created_or_existing:
        print(f"{experiment['name']}: {experiment['status']} ({experiment['id']})")
    print("Open http://localhost:3000/experiments to watch and compare real results.")


if __name__ == "__main__":
    main()
