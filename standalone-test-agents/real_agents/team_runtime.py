from __future__ import annotations

import asyncio
import os
import time
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request

from real_agents.product_team import (
    BACKEND_AGENT,
    FRONTEND_AGENT,
    QA_AGENT,
    QUALITY_AGENT,
    UIUX_AGENT,
)
from real_agents.runtime import (
    DEFAULT_MODEL,
    AgentSpec,
    InvocationRequest,
    ModelGateway,
    ModelResult,
    calculate_cost,
    configured_gateway,
    generate_model,
    max_output_tokens_from_configuration,
    model_from_configuration,
    model_span,
    tool_span,
)

TEAM_NAME = "product-delivery-team"
TEAM_VERSION = "product-team-v1-real"


async def _run_role(
    *,
    gateway: ModelGateway,
    spec: AgentSpec,
    value: Any,
    context: Any | None,
    model: str,
    max_output_tokens: int,
) -> tuple[ModelResult, dict[str, Any]]:
    prepared = spec.prepare(value, context)
    result, latency_ms = await generate_model(
        gateway,
        agent_name=spec.name,
        model=model,
        instructions=spec.instructions,
        prompt=prepared.prompt,
        web_search=spec.web_search,
        max_output_tokens=max_output_tokens,
    )
    span = model_span(
        name=spec.name,
        prompt=prepared.prompt,
        result=result,
        latency_ms=latency_ms,
        metadata={"role": spec.title, "agent_version": spec.version},
    )
    return result, span


def create_product_team_app() -> FastAPI:
    app = FastAPI(title="Real coordinated product delivery team", version=TEAM_VERSION)
    app.state.gateway = None

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "agent": TEAM_NAME,
            "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
            "model_calls_per_invocation": 5,
        }

    @app.post("/invoke")
    async def invoke(invocation: InvocationRequest, http_request: Request) -> dict[str, Any]:
        model = model_from_configuration(invocation.configuration)
        max_output_tokens = max_output_tokens_from_configuration(invocation.configuration)
        gateway: ModelGateway = http_request.app.state.gateway or configured_gateway()
        workflow_started = time.perf_counter()

        design, design_span = await _run_role(
            gateway=gateway,
            spec=UIUX_AGENT,
            value=invocation.input,
            context=invocation.context,
            model=model,
            max_output_tokens=max_output_tokens,
        )
        development_context = {
            "request_context": invocation.context,
            "ui_ux_specification": design.text,
        }
        (frontend, frontend_span), (backend, backend_span) = await asyncio.gather(
            _run_role(
                gateway=gateway,
                spec=FRONTEND_AGENT,
                value=invocation.input,
                context=development_context,
                model=model,
                max_output_tokens=max_output_tokens,
            ),
            _run_role(
                gateway=gateway,
                spec=BACKEND_AGENT,
                value=invocation.input,
                context=development_context,
                model=model,
                max_output_tokens=max_output_tokens,
            ),
        )
        test_context = {
            "request_context": invocation.context,
            "ui_ux_specification": design.text,
            "frontend_plan": frontend.text,
            "backend_plan": backend.text,
        }
        (qa, qa_span), (quality, quality_span) = await asyncio.gather(
            _run_role(
                gateway=gateway,
                spec=QA_AGENT,
                value=invocation.input,
                context=test_context,
                model=model,
                max_output_tokens=max_output_tokens,
            ),
            _run_role(
                gateway=gateway,
                spec=QUALITY_AGENT,
                value=invocation.input,
                context=test_context,
                model=model,
                max_output_tokens=max_output_tokens,
            ),
        )

        results = [design, frontend, backend, qa, quality]
        total_cost = sum(
            (
                calculate_cost(result.model, result.input_tokens, result.output_tokens)
                for result in results
            ),
            start=Decimal("0"),
        )
        input_tokens = sum(result.input_tokens for result in results)
        output_tokens = sum(result.output_tokens for result in results)
        total_tokens = sum(result.total_tokens for result in results)
        artifacts = {
            "ui_ux_design": design.text,
            "frontend_implementation": frontend.text,
            "backend_implementation": backend.text,
            "qa_test_plan": qa.text,
            "accessibility_performance_plan": quality.text,
        }
        workflow_latency_ms = round((time.perf_counter() - workflow_started) * 1000)

        return {
            "output": {
                "answer": (
                    "The five-agent product team completed the design, development, and testing "
                    "handoffs."
                ),
                "artifacts": artifacts,
            },
            "metadata": {
                "agent": TEAM_NAME,
                "agent_version": TEAM_VERSION,
                "provider": "openai",
                "model": model,
                "workflow": "design -> parallel development -> parallel testing",
                "response_ids": {
                    "ui_ux_design": design.response_id,
                    "frontend_implementation": frontend.response_id,
                    "backend_implementation": backend.response_id,
                    "qa_test_plan": qa.response_id,
                    "accessibility_performance_plan": quality.response_id,
                },
                "workflow_latency_ms": workflow_latency_ms,
            },
            "spans": [
                design_span,
                tool_span(
                    "handoff_to_development",
                    {"from": UIUX_AGENT.name},
                    {"to": [FRONTEND_AGENT.name, BACKEND_AGENT.name]},
                ),
                frontend_span,
                backend_span,
                tool_span(
                    "handoff_to_testing",
                    {"from": [FRONTEND_AGENT.name, BACKEND_AGENT.name]},
                    {"to": [QA_AGENT.name, QUALITY_AGENT.name]},
                ),
                qa_span,
                quality_span,
            ],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "total_cost": float(total_cost),
            },
        }

    return app
