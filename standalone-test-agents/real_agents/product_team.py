from __future__ import annotations

import json
from typing import Any

from real_agents.runtime import AgentSpec, PreparedPrompt

MAX_PROMPT_VALUE_CHARS = 20_000


def _serialize(value: Any) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        serialized = str(value)
    if len(serialized) <= MAX_PROMPT_VALUE_CHARS:
        return serialized
    return serialized[:MAX_PROMPT_VALUE_CHARS] + "\n… [input truncated by the agent]"


def _role_prompt(
    *,
    role: str,
    deliverable: str,
    value: Any,
    context: Any | None,
) -> PreparedPrompt:
    return PreparedPrompt(
        prompt=(
            f"You are the {role} in a cross-functional product team.\n\n"
            f"Product brief:\n{_serialize(value)}\n\n"
            f"Additional context and upstream work:\n{_serialize(context or {})}\n\n"
            f"Required deliverable:\n{deliverable}\n\n"
            "Be concrete, resolve ambiguity with clearly labeled assumptions, identify risks, and "
            "make the output directly actionable for the next specialist. Do not claim that code, "
            "tests, deployments, or user research were executed unless evidence is supplied."
        )
    )


def prepare_uiux(value: Any, context: Any | None) -> PreparedPrompt:
    return _role_prompt(
        role="senior UI/UX designer",
        deliverable=(
            "Create a concise experience specification with user goals, primary journey, "
            "information architecture, screen/component inventory, interaction states, "
            "responsive behavior, accessibility requirements, design tokens, and developer-ready "
            "acceptance criteria."
        ),
        value=value,
        context=context,
    )


def prepare_frontend(value: Any, context: Any | None) -> PreparedPrompt:
    return _role_prompt(
        role="senior frontend developer",
        deliverable=(
            "Produce a production implementation plan covering component boundaries, state and "
            "data flow, routing, validation, error/loading/empty states, accessibility, "
            "responsive styling, security, tests, and representative typed code or interfaces "
            "where useful."
        ),
        value=value,
        context=context,
    )


def prepare_backend(value: Any, context: Any | None) -> PreparedPrompt:
    return _role_prompt(
        role="senior backend developer",
        deliverable=(
            "Produce a production backend design covering API contracts, domain model, "
            "persistence, "
            "authorization and tenant isolation, validation, idempotency, observability, failure "
            "handling, migrations, tests, and representative schemas or pseudocode where useful."
        ),
        value=value,
        context=context,
    )


def prepare_qa(value: Any, context: Any | None) -> PreparedPrompt:
    return _role_prompt(
        role="senior QA automation engineer",
        deliverable=(
            "Create a risk-based test strategy with traceable acceptance criteria, unit, "
            "integration, and E2E coverage; positive and negative cases; test data; concurrency "
            "and "
            "failure scenarios; "
            "automation priorities, release gates, and a concise go/no-go checklist."
        ),
        value=value,
        context=context,
    )


def prepare_quality(value: Any, context: Any | None) -> PreparedPrompt:
    return _role_prompt(
        role="accessibility and performance test specialist",
        deliverable=(
            "Create an accessibility and performance verification plan covering WCAG 2.2 AA, "
            "keyboard and screen-reader behavior, contrast and motion, Core Web Vitals, API "
            "latency "
            "and load budgets, tooling, reproducible checks, failure thresholds, and remediation "
            "priorities."
        ),
        value=value,
        context=context,
    )


UIUX_AGENT = AgentSpec(
    name="uiux-designer-agent",
    title="Real UI/UX designer agent",
    version="uiux-v1-real",
    instructions=(
        "You are a principal product designer. Optimize for clarity, inclusive interaction, "
        "coherent systems, and feasible handoff. Avoid decorative complexity without a user "
        "benefit."
    ),
    prepare=prepare_uiux,
)

FRONTEND_AGENT = AgentSpec(
    name="frontend-developer-agent",
    title="Real frontend developer agent",
    version="frontend-v1-real",
    instructions=(
        "You are a principal frontend engineer. Prefer accessible semantic interfaces, typed "
        "contracts, small composable components, deterministic state, and verifiable "
        "implementation "
        "details."
    ),
    prepare=prepare_frontend,
)

BACKEND_AGENT = AgentSpec(
    name="backend-developer-agent",
    title="Real backend developer agent",
    version="backend-v1-real",
    instructions=(
        "You are a principal backend engineer. Design secure tenant-safe APIs, explicit "
        "invariants, "
        "reliable persistence, observable operations, and controlled failure behavior."
    ),
    prepare=prepare_backend,
)

QA_AGENT = AgentSpec(
    name="qa-engineer-agent",
    title="Real QA engineer agent",
    version="qa-v1-real",
    instructions=(
        "You are a principal QA automation engineer. Convert requirements and implementation plans "
        "into risk-based, reproducible tests and measurable release gates."
    ),
    prepare=prepare_qa,
)

QUALITY_AGENT = AgentSpec(
    name="quality-specialist-agent",
    title="Real accessibility and performance agent",
    version="quality-v1-real",
    instructions=(
        "You are a specialist in accessibility and performance testing. Use measurable criteria, "
        "prioritize user impact, and distinguish automated coverage from required manual testing."
    ),
    prepare=prepare_quality,
)

PRODUCT_TEAM_AGENTS = (
    UIUX_AGENT,
    FRONTEND_AGENT,
    BACKEND_AGENT,
    QA_AGENT,
    QUALITY_AGENT,
)
