from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from httpx import AsyncClient
from pytest import MonkeyPatch
from test_tracing_api import _workspace

from agentscope_api.core.config import Settings
from agentscope_api.models import FailureRecord, SpanType
from agentscope_api.services.failure_intelligence import (
    FailureIntelligenceService,
    QdrantFailureIndex,
    density_clusters,
    detect_agent_loop,
    hashing_embedding,
)


async def _failed_trace(client: AsyncClient, project_id: str, api_key: str) -> str:
    now = datetime.now(UTC)
    external_id = str(uuid4())
    events: list[dict[str, object]] = [
        {
            "event_id": str(uuid4()),
            "timestamp": now.isoformat(),
            "type": "TRACE_START",
            "trace_id": external_id,
            "payload": {
                "name": "looping-support-agent",
                "input": {"question": "Find order A-42"},
                "agent_version": "broken-v1",
            },
        }
    ]
    for index in range(3):
        span_id = str(uuid4())
        events.extend(
            [
                {
                    "event_id": str(uuid4()),
                    "timestamp": (now + timedelta(milliseconds=index * 10 + 1)).isoformat(),
                    "type": "SPAN_START",
                    "trace_id": external_id,
                    "span_id": span_id,
                    "payload": {"name": "search-order", "span_type": "TOOL"},
                },
                {
                    "event_id": str(uuid4()),
                    "timestamp": (now + timedelta(milliseconds=index * 10 + 5)).isoformat(),
                    "type": "SPAN_END",
                    "trace_id": external_id,
                    "span_id": span_id,
                    "payload": {"status": "SUCCESS", "output": {"found": False}},
                },
            ]
        )
    events.append(
        {
            "event_id": str(uuid4()),
            "timestamp": (now + timedelta(milliseconds=50)).isoformat(),
            "type": "TRACE_END",
            "trace_id": external_id,
            "payload": {
                "status": "ERROR",
                "error_type": "TOOL_ERROR",
                "error_message": "Order lookup exhausted",
            },
        }
    )
    response = await client.post(
        "/v1/ingest/batch",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"sdk": {"name": "test", "version": "1"}, "events": events},
    )
    assert response.status_code == 202, response.text
    return external_id


async def test_failure_analysis_search_clustering_and_tenant_isolation(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    async def no_index(self: QdrantFailureIndex, record: object) -> None:
        return None

    async def unavailable_search(self: QdrantFailureIndex, *args: object) -> object:
        raise httpx.ConnectError("Qdrant unavailable")

    monkeypatch.setattr(QdrantFailureIndex, "upsert", no_index)
    monkeypatch.setattr(QdrantFailureIndex, "search", unavailable_search)
    headers, project_id, api_key = await _workspace(client, "failures@example.com")
    external_ids = [
        await _failed_trace(client, project_id, api_key),
        await _failed_trace(client, project_id, api_key),
    ]
    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    trace_ids = [
        item["id"] for item in traces.json()["items"] if item["external_trace_id"] in external_ids
    ]
    for trace_id in trace_ids:
        analyzed = await client.post(
            f"/api/v1/projects/{project_id}/traces/{trace_id}/failure-analysis",
            headers=headers,
        )
        assert analyzed.status_code == 200, analyzed.text
        assert analyzed.json()["failure_type"] == "TOOL_ERROR"
        assert analyzed.json()["evidence"]["loop_detection"]["possible_agent_loop"] is True
        assert len(analyzed.json()["document"]) <= 16_000

    search = await client.post(
        f"/api/v1/projects/{project_id}/failures/search",
        headers=headers,
        json={"query": "order search tool exhausted", "limit": 10},
    )
    assert search.status_code == 200, search.text
    assert len(search.json()) == 2
    assert all(-1 <= item["similarity"] <= 1 for item in search.json())

    rebuilt = await client.post(
        f"/api/v1/projects/{project_id}/failure-clusters/rebuild", headers=headers
    )
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()[0]["size"] == 2
    assert rebuilt.json()[0]["summary_source"] == "HEURISTIC_INFERENCE"
    cluster_id = rebuilt.json()[0]["id"]
    cluster = await client.get(
        f"/api/v1/projects/{project_id}/failure-clusters/{cluster_id}", headers=headers
    )
    assert len(cluster.json()["failure_ids"]) == 2

    foreign_headers, foreign_project_id, _ = await _workspace(
        client, "foreign-failures@example.com"
    )
    failure_id = search.json()[0]["failure"]["id"]
    hidden = await client.get(
        f"/api/v1/projects/{foreign_project_id}/failures/{failure_id}",
        headers=foreign_headers,
    )
    assert hidden.status_code == 404


def test_embedding_clustering_and_loop_heuristics() -> None:
    first = hashing_embedding("tool failed to find order")
    second = hashing_embedding("tool failed to find order")
    unrelated = hashing_embedding("hallucinated refund policy")
    assert len(first) == 128
    assert density_clusters([first, second, unrelated]) == [[0, 1]]

    class ToolSpan:
        type = SpanType.TOOL
        name = "search"

    spans = [ToolSpan(), ToolSpan(), ToolSpan()]
    result = detect_agent_loop(spans)  # type: ignore[arg-type]
    assert result["possible_agent_loop"] is True
    assert result["evidence"][0]["heuristic"] == "repeated_tool"


async def test_qdrant_search_always_includes_tenant_and_project_filters(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["api_key"] = request.headers.get("api-key")
        if request.method == "GET":
            return httpx.Response(200, json={"result": {"status": "green"}})
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"result": []})

    index = QdrantFailureIndex("http://qdrant", "qdrant-test-key")
    organization_id = uuid4()
    project_id = uuid4()

    class TestClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", TestClient)
    await index.search(organization_id, project_id, [0.0] * 128, 5)
    filters = captured["filter"]  # type: ignore[index]
    values = {item["key"]: item["match"]["value"] for item in filters["must"]}  # type: ignore[index]
    assert values == {
        "organization_id": str(organization_id),
        "project_id": str(project_id),
    }
    assert captured["api_key"] == "qdrant-test-key"


async def test_worker_can_analyze_and_recluster_with_dedicated_credential(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    async def no_index(self: QdrantFailureIndex, record: object) -> None:
        return None

    monkeypatch.setattr(QdrantFailureIndex, "upsert", no_index)
    headers, project_id, api_key = await _workspace(client, "failure-worker@example.com")
    external_id = await _failed_trace(client, project_id, api_key)
    traces = await client.get(f"/api/v1/projects/{project_id}/traces", headers=headers)
    trace_id = next(
        item["id"] for item in traces.json()["items"] if item["external_trace_id"] == external_id
    )

    rejected = await client.post(f"/internal/v1/failures/analyze/{trace_id}")
    assert rejected.status_code == 401
    analyzed = await client.post(
        f"/internal/v1/failures/analyze/{trace_id}",
        headers={"X-AgentScope-Worker-Key": "development-only-worker-key-change-me"},
    )
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["failure_type"] == "TOOL_ERROR"


async def test_cluster_summary_uses_validated_structured_output(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class StructuredClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "StructuredClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> httpx.Response:
            captured.update(kwargs["json"])  # type: ignore[arg-type]
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": __import__("json").dumps(
                                        {
                                            "title": "Repeated lookup exhaustion",
                                            "description": "Order lookup retries recur.",
                                            "probable_cause": (
                                                "The tool may return ambiguous misses."
                                            ),
                                            "suggested_action": "Add a bounded retry policy.",
                                        }
                                    ),
                                }
                            ],
                        }
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", StructuredClient)
    settings = Settings(OPENAI_API_KEY="test-provider-key")
    service = FailureIntelligenceService(None, settings)  # type: ignore[arg-type]
    summary, source = await service._summarize_cluster(  # noqa: SLF001
        [FailureRecord(title="Lookup failed", document='{"error":"lookup"}')],
        "TOOL_ERROR",
    )
    assert summary.title == "Repeated lookup exhaustion"
    assert source == "OPENAI_STRUCTURED_INFERENCE"
    assert captured["text"]["format"]["strict"] is True  # type: ignore[index]
