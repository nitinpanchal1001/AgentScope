from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from pytest import MonkeyPatch
from test_tracing_api import _workspace

WORKER_HEADERS = {"X-AgentScope-Worker-Key": "development-only-worker-key-change-me"}


async def _production_trace(
    client: AsyncClient, project_id: str, api_key: str
) -> tuple[str, dict[str, object]]:
    now = datetime.now(UTC)
    external_trace_id = str(uuid4())
    span_id = str(uuid4())
    original_output = {"answer": "Your order shipped."}
    events = [
        {
            "event_id": str(uuid4()),
            "timestamp": now.isoformat(),
            "type": "TRACE_START",
            "trace_id": external_trace_id,
            "payload": {
                "name": "support-agent",
                "input": {"message": "Where is order A-42?"},
                "agent_version": "support-v1",
                "metadata": {
                    "configuration": {
                        "model": "baseline-model",
                        "prompt_version": "support-v1",
                        "temperature": 0.2,
                        "parameters": {"max_steps": 4},
                    }
                },
                "tags": ["production"],
            },
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=5)).isoformat(),
            "type": "SPAN_START",
            "trace_id": external_trace_id,
            "span_id": span_id,
            "payload": {
                "name": "lookup-order",
                "span_type": "TOOL",
                "model": "baseline-model",
            },
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=30)).isoformat(),
            "type": "SPAN_END",
            "trace_id": external_trace_id,
            "span_id": span_id,
            "payload": {"status": "SUCCESS", "output": {"state": "shipped"}},
        },
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=40)).isoformat(),
            "type": "TRACE_END",
            "trace_id": external_trace_id,
            "payload": {
                "status": "SUCCESS",
                "output": original_output,
                "latency_ms": 40,
                "total_tokens": 17,
                "cost": "0.002",
            },
        },
    ]
    ingested = await client.post(
        "/v1/ingest/batch",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"sdk": {"name": "agentscope-python", "version": "0.8.0"}, "events": events},
    )
    assert ingested.status_code == 202, ingested.text
    traces = await client.get(
        f"/api/v1/projects/{project_id}/traces",
        headers={},
    )
    assert traces.status_code == 401
    return external_trace_id, original_output


async def test_replay_creates_new_trace_clones_evaluations_and_compares(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agentscope_api.api.routers.replays.dispatch_replay", lambda replay_id: True
    )
    monkeypatch.setattr(
        "agentscope_api.api.routers.evaluations.dispatch_evaluation", lambda result_id: True
    )
    headers, project_id, api_key = await _workspace(client, "replay-owner@example.com")
    external_trace_id, original_output = await _production_trace(client, project_id, api_key)
    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    original = next(
        item for item in traces.json()["items"] if item["external_trace_id"] == external_trace_id
    )
    original_id = original["id"]

    evaluator = await client.post(
        f"/api/v1/projects/{project_id}/evaluators",
        headers=headers,
        json={
            "name": "Replay correctness",
            "version": {"type": "EXACT_MATCH", "configuration": {}, "threshold": "1"},
        },
    )
    evaluator_version_id = evaluator.json()["versions"][0]["id"]
    manual = await client.post(
        f"/api/v1/projects/{project_id}/traces/{original_id}/evaluations",
        headers=headers,
        json={"evaluator_version_ids": [evaluator_version_id]},
    )
    original_result_id = manual.json()[0]["id"]
    completed_original = await client.post(
        f"/internal/v1/evaluation-results/{original_result_id}/complete",
        headers=WORKER_HEADERS,
        json={"status": "SUCCESS", "score": "1", "passed": True, "label": "PASS"},
    )
    assert completed_original.status_code == 204

    created = await client.post(
        f"/api/v1/projects/{project_id}/traces/{original_id}/replays",
        headers=headers,
        json={
            "agent": {
                "endpoint": "https://candidate.example.com/invoke",
                "provider": "test-provider",
            },
            "overrides": {
                "model": "candidate-model",
                "prompt_version": "support-v2",
                "temperature": 0.1,
                "agent_version": "agent-v2",
                "parameters": {"max_steps": 6},
            },
        },
    )
    assert created.status_code == 202, created.text
    replay_id = created.json()["id"]
    assert created.json()["status"] == "RUNNING"
    assert created.json()["effective_configuration"]["model"] == "candidate-model"

    payload = await client.get(f"/internal/v1/replays/{replay_id}/payload", headers=WORKER_HEADERS)
    assert payload.status_code == 200, payload.text
    assert payload.json()["request"]["input"] == {"message": "Where is order A-42?"}
    assert payload.json()["request"]["configuration"]["prompt_version"] == "support-v2"
    assert payload.json()["headers_from_env"] == {}

    invocation = await client.post(
        f"/internal/v1/replays/{replay_id}/complete",
        headers=WORKER_HEADERS,
        json={
            "status": "SUCCESS",
            "output": {"answer": "Order A-42 is in transit."},
            "metadata": {"fixture": True},
            "spans": [
                {
                    "type": "TOOL",
                    "name": "search-shipment",
                    "model": "candidate-model",
                    "latency_ms": 50,
                    "total_tokens": 23,
                    "cost": "0.003",
                }
            ],
            "latency_ms": 50,
            "total_tokens": 23,
            "total_cost": "0.003",
        },
    )
    assert invocation.status_code == 200, invocation.text
    assert invocation.json()["status"] == "EVALUATING"
    assert invocation.json()["replay_trace_id"] != original_id
    assert len(invocation.json()["evaluation_result_ids"]) == 1
    replay_trace_id = invocation.json()["replay_trace_id"]

    repeated = await client.post(
        f"/internal/v1/replays/{replay_id}/complete",
        headers=WORKER_HEADERS,
        json={"status": "FAILED", "error_message": "must be ignored"},
    )
    assert repeated.json()["replay_trace_id"] == replay_trace_id
    assert repeated.json()["evaluation_result_ids"] == []

    replay_result_id = invocation.json()["evaluation_result_ids"][0]
    completed_replay = await client.post(
        f"/internal/v1/evaluation-results/{replay_result_id}/complete",
        headers=WORKER_HEADERS,
        json={"status": "SUCCESS", "score": "0.5", "passed": False, "label": "FAIL"},
    )
    assert completed_replay.status_code == 204
    replay = await client.get(f"/api/v1/projects/{project_id}/replays/{replay_id}", headers=headers)
    assert replay.json()["status"] == "COMPLETED"

    comparison = await client.get(
        f"/api/v1/projects/{project_id}/replays/{replay_id}/comparison", headers=headers
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["original"]["output"] == original_output
    assert comparison.json()["replay"]["trace_id"] == replay_trace_id
    assert comparison.json()["differences"]["output_changed"] is True
    assert comparison.json()["differences"]["evaluation_score_delta"] == -0.5
    assert comparison.json()["differences"]["tool_sequence_changed"] is True
    assert comparison.json()["original"]["tool_sequence"] == ["lookup-order"]
    assert comparison.json()["replay"]["tool_sequence"] == ["search-shipment"]

    original_after = await client.get(f"/api/v1/traces/{original_id}", headers=headers)
    assert original_after.json()["output"] == original_output
    assert original_after.json()["external_trace_id"] == external_trace_id
    generated = await client.get(f"/api/v1/traces/{replay_trace_id}", headers=headers)
    assert generated.json()["metadata"]["original_trace_id"] == original_id

    listed = await client.get(
        f"/api/v1/projects/{project_id}/traces/{original_id}/replays", headers=headers
    )
    assert listed.json()[0]["id"] == replay_id

    foreign_headers, foreign_project_id, _ = await _workspace(client, "foreign-replay@example.com")
    hidden = await client.get(
        f"/api/v1/projects/{foreign_project_id}/replays/{replay_id}",
        headers=foreign_headers,
    )
    assert hidden.status_code == 404


async def test_replay_dispatch_failure_is_durable(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agentscope_api.api.routers.replays.dispatch_replay", lambda replay_id: False
    )
    headers, project_id, api_key = await _workspace(client, "replay-dispatch@example.com")
    external_id, _ = await _production_trace(client, project_id, api_key)
    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    trace_id = next(
        item["id"] for item in traces.json()["items"] if item["external_trace_id"] == external_id
    )
    replay = await client.post(
        f"/api/v1/projects/{project_id}/traces/{trace_id}/replays",
        headers=headers,
        json={"agent": {"endpoint": "https://candidate.example.com/invoke"}},
    )
    assert replay.status_code == 202
    assert replay.json()["status"] == "FAILED"
    assert replay.json()["error_type"] == "DISPATCH_FAILED"
