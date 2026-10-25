from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("agentscope.real_agents")

DEFAULT_MODEL = "gpt-6-luna"
MODEL_PRICING_PER_MILLION = {
    "gpt-6-luna": (Decimal("0.1"), Decimal("0.5")),
    "gpt-6.1-sol": (Decimal("2"), Decimal("10")),
    "gpt-6-astra": (Decimal("10"), Decimal("50")),
}


class InvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Any
    context: Any | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ModelResult:
    text: str
    model: str
    response_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ModelGateway(Protocol):
    async def generate(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        web_search: bool,
        max_output_tokens: int,
    ) -> ModelResult: ...


class OpenAIResponsesGateway:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        options: dict[str, Any] = {
            "api_key": api_key,
            "max_retries": 2,
            "timeout": 90,
        }
        if base_url := os.getenv("OPENAI_BASE_URL"):
            options["base_url"] = base_url
        self.client = AsyncOpenAI(**options)

    async def generate(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        web_search: bool,
        max_output_tokens: int,
    ) -> ModelResult:
        request: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        if web_search:
            request["tools"] = [{"type": "web_search"}]
        response = await self.client.responses.create(**request)
        text = response.output_text.strip()
        if not text:
            raise ValueError("The model returned no text output")
        usage = response.usage
        input_tokens = int(usage.input_tokens) if usage else 0
        output_tokens = int(usage.output_tokens) if usage else 0
        total_tokens = int(usage.total_tokens) if usage else input_tokens + output_tokens
        return ModelResult(
            text=text,
            model=str(response.model or model),
            response_id=response.id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )


@dataclass(frozen=True)
class PreparedPrompt:
    prompt: str
    spans: list[dict[str, Any]] = field(default_factory=list)


PreparePrompt = Callable[[Any, Any | None], PreparedPrompt]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    title: str
    version: str
    instructions: str
    prepare: PreparePrompt
    web_search: bool = False


def tool_span(name: str, tool_input: Any, output: Any, *, latency_ms: int = 0) -> dict[str, Any]:
    return {
        "type": "TOOL",
        "name": name,
        "input": tool_input,
        "output": output,
        "latency_ms": latency_ms,
        "status": "SUCCESS",
    }


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    configured_input = os.getenv("OPENAI_INPUT_PRICE_PER_MILLION")
    configured_output = os.getenv("OPENAI_OUTPUT_PRICE_PER_MILLION")
    pricing: tuple[Decimal, Decimal] | None
    if configured_input is not None and configured_output is not None:
        pricing = (Decimal(configured_input), Decimal(configured_output))
    else:
        pricing = MODEL_PRICING_PER_MILLION.get(model)
    if pricing is None:
        return Decimal("0")
    return (Decimal(input_tokens) * pricing[0] + Decimal(output_tokens) * pricing[1]) / Decimal(
        "1000000"
    )


def model_span(
    *,
    name: str,
    prompt: str,
    result: ModelResult,
    latency_ms: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cost = calculate_cost(result.model, result.input_tokens, result.output_tokens)
    return {
        "type": "LLM",
        "name": name,
        "provider": "openai",
        "model": result.model,
        "input": {"prompt": prompt},
        "output": result.text,
        "latency_ms": latency_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "cost": str(cost),
        "status": "SUCCESS",
        "metadata": {
            "response_id": result.response_id,
            "stored": False,
            **(metadata or {}),
        },
    }


def model_from_configuration(configuration: dict[str, Any]) -> str:
    value = configuration.get("model") or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise HTTPException(
            status_code=422, detail="configuration.model must be a valid model name"
        )
    return value.strip()


def max_output_tokens_from_configuration(configuration: dict[str, Any]) -> int:
    value = configuration.get("max_output_tokens", 700)
    if not isinstance(value, int) or isinstance(value, bool) or not 64 <= value <= 4096:
        raise HTTPException(
            status_code=422,
            detail="configuration.max_output_tokens must be an integer from 64 to 4096",
        )
    return value


def configured_gateway() -> ModelGateway:
    try:
        return OpenAIResponsesGateway()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


async def generate_model(
    gateway: ModelGateway,
    *,
    agent_name: str,
    model: str,
    instructions: str,
    prompt: str,
    web_search: bool,
    max_output_tokens: int,
) -> tuple[ModelResult, int]:
    started = time.perf_counter()
    try:
        result = await gateway.generate(
            model=model,
            instructions=instructions,
            prompt=prompt,
            web_search=web_search,
            max_output_tokens=max_output_tokens,
        )
    except AuthenticationError as error:
        logger.warning("openai.authentication_failed", extra={"agent": agent_name})
        raise HTTPException(status_code=502, detail="OpenAI authentication failed") from error
    except RateLimitError as error:
        logger.warning("openai.rate_limited", extra={"agent": agent_name})
        raise HTTPException(status_code=429, detail="OpenAI rate limit exceeded") from error
    except (APIConnectionError, APITimeoutError) as error:
        logger.warning("openai.unavailable", extra={"agent": agent_name})
        raise HTTPException(status_code=503, detail="OpenAI is temporarily unavailable") from error
    except APIStatusError as error:
        logger.warning(
            "openai.request_failed",
            extra={"agent": agent_name, "provider_status": error.status_code},
        )
        status = 503 if error.status_code >= 500 else 502
        raise HTTPException(status_code=status, detail="OpenAI request failed") from error
    return result, round((time.perf_counter() - started) * 1000)


def create_agent_app(spec: AgentSpec) -> FastAPI:
    app = FastAPI(title=spec.title, version=spec.version)
    app.state.gateway = None

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "agent": spec.name,
            "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        }

    @app.post("/invoke")
    async def invoke(invocation: InvocationRequest, http_request: Request) -> dict[str, Any]:
        prepared = spec.prepare(invocation.input, invocation.context)
        model = model_from_configuration(invocation.configuration)
        max_output_tokens = max_output_tokens_from_configuration(invocation.configuration)
        gateway: ModelGateway = http_request.app.state.gateway or configured_gateway()
        result, latency_ms = await generate_model(
            gateway,
            agent_name=spec.name,
            model=model,
            instructions=spec.instructions,
            prompt=prepared.prompt,
            web_search=spec.web_search,
            max_output_tokens=max_output_tokens,
        )
        cost = calculate_cost(result.model, result.input_tokens, result.output_tokens)
        spans = [
            *prepared.spans,
            model_span(
                name="openai-response",
                prompt=prepared.prompt,
                result=result,
                latency_ms=latency_ms,
            ),
        ]
        return {
            "output": {"answer": result.text},
            "metadata": {
                "agent": spec.name,
                "agent_version": spec.version,
                "provider": "openai",
                "model": result.model,
                "response_id": result.response_id,
            },
            "spans": spans,
            "usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "total_cost": float(cost),
            },
        }

    return app
