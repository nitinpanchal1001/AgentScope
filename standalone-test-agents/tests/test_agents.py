from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from real_agents.product_team import (
    BACKEND_AGENT,
    FRONTEND_AGENT,
    QA_AGENT,
    QUALITY_AGENT,
    UIUX_AGENT,
)
from real_agents.runtime import ModelResult, create_agent_app
from real_agents.specs import (
    DATA_ANALYST_AGENT,
    FAQ_AGENT,
    INCIDENT_AGENT,
    RESEARCH_AGENT,
    TRAVEL_AGENT,
)
from real_agents.team_runtime import create_product_team_app


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        web_search: bool,
        max_output_tokens: int,
    ) -> ModelResult:
        self.calls.append(
            {
                "model": model,
                "instructions": instructions,
                "prompt": prompt,
                "web_search": web_search,
                "max_output_tokens": max_output_tokens,
            }
        )
        return ModelResult(
            text="A real provider response.",
            model=model,
            response_id="resp_test",
            input_tokens=100,
            output_tokens=25,
            total_tokens=125,
        )


@pytest.mark.parametrize(
    ("spec", "agent_input", "expected_tools", "uses_web_search"),
    [
        (FAQ_AGENT, {"question": "How long is shipping?"}, ["search_knowledge_base"], False),
        (
            RESEARCH_AGENT,
            {"question": "What changed in AI evaluation?"},
            ["openai_web_search"],
            True,
        ),
        (
            DATA_ANALYST_AGENT,
            {"question": "Summarize", "records": [{"revenue": 10}, {"revenue": 20}]},
            ["profile_records"],
            False,
        ),
        (
            TRAVEL_AGENT,
            {"origin": "Delhi", "destination": "Tokyo", "budget": "moderate"},
            ["search_travel_information"],
            True,
        ),
        (
            INCIDENT_AGENT,
            {"service": "checkout", "signal": "latency", "metrics": {"p95": 4000}},
            ["fetch_service_health", "lookup_runbook"],
            False,
        ),
        (
            UIUX_AGENT,
            {"brief": "Design an agent onboarding flow"},
            [],
            False,
        ),
        (
            FRONTEND_AGENT,
            {"brief": "Build an accessible experiment wizard"},
            [],
            False,
        ),
        (
            BACKEND_AGENT,
            {"brief": "Design a tenant-safe experiments API"},
            [],
            False,
        ),
        (
            QA_AGENT,
            {"brief": "Test a concurrent experiment runner"},
            [],
            False,
        ),
        (
            QUALITY_AGENT,
            {"brief": "Audit dashboard accessibility and performance"},
            [],
            False,
        ),
    ],
)
def test_agent_returns_agentscope_contract(
    spec: Any,
    agent_input: dict[str, Any],
    expected_tools: list[str],
    uses_web_search: bool,
) -> None:
    app = create_agent_app(spec)
    gateway = FakeGateway()
    app.state.gateway = gateway

    response = TestClient(app).post(
        "/invoke",
        json={
            "input": agent_input,
            "configuration": {"model": "gpt-6-luna", "max_output_tokens": 300},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output"] == {"answer": "A real provider response."}
    assert body["usage"] == {
        "input_tokens": 100,
        "output_tokens": 25,
        "total_tokens": 125,
        "total_cost": 0.0000225,
    }
    assert [span["name"] for span in body["spans"][:-1]] == expected_tools
    assert body["spans"][-1]["type"] == "LLM"
    assert body["spans"][-1]["metadata"]["response_id"] == "resp_test"
    assert gateway.calls[0]["web_search"] is uses_web_search


def test_missing_openai_key_fails_without_calling_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_agent_app(FAQ_AGENT)

    response = TestClient(app).post(
        "/invoke",
        json={"input": {"question": "What is the warranty?"}},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "OPENAI_API_KEY is required"}


def test_health_does_not_make_a_provider_call() -> None:
    app = create_agent_app(FAQ_AGENT)
    gateway = FakeGateway()
    app.state.gateway = gateway

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["agent"] == "faq-agent"
    assert gateway.calls == []


def test_product_team_coordinates_five_real_model_calls() -> None:
    app = create_product_team_app()
    gateway = FakeGateway()
    app.state.gateway = gateway

    response = TestClient(app).post(
        "/invoke",
        json={
            "input": {
                "brief": "Build a customer feedback portal",
                "stack": "Next.js, FastAPI, PostgreSQL",
            },
            "configuration": {"model": "gpt-6-luna", "max_output_tokens": 300},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(gateway.calls) == 5
    assert set(body["output"]["artifacts"]) == {
        "ui_ux_design",
        "frontend_implementation",
        "backend_implementation",
        "qa_test_plan",
        "accessibility_performance_plan",
    }
    assert [span["name"] for span in body["spans"]] == [
        "uiux-designer-agent",
        "handoff_to_development",
        "frontend-developer-agent",
        "backend-developer-agent",
        "handoff_to_testing",
        "qa-engineer-agent",
        "quality-specialist-agent",
    ]
    assert body["usage"] == {
        "input_tokens": 500,
        "output_tokens": 125,
        "total_tokens": 625,
        "total_cost": 0.0001125,
    }
    assert "ui_ux_specification" in gateway.calls[1]["prompt"]
    assert "frontend_plan" in gateway.calls[3]["prompt"]


def test_product_team_health_reports_billing_shape() -> None:
    app = create_product_team_app()
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["agent"] == "product-delivery-team"
    assert response.json()["model_calls_per_invocation"] == 5
