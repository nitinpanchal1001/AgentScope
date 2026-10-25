from __future__ import annotations

import json
from statistics import mean
from typing import Any

from real_agents.runtime import AgentSpec, PreparedPrompt, tool_span

FAQ_KNOWLEDGE = [
    {
        "id": "shipping",
        "text": (
            "Standard shipping takes 3–5 business days. Express shipping takes 1–2 business days."
        ),
    },
    {
        "id": "returns",
        "text": (
            "Unused products may be returned within 30 days of delivery with the order receipt."
        ),
    },
    {
        "id": "warranty",
        "text": "Hardware includes a 12-month limited warranty covering manufacturing defects.",
    },
    {
        "id": "support-hours",
        "text": "Human support is available Monday through Friday, 09:00–18:00 UTC.",
    },
]

RUNBOOKS = {
    "latency": (
        "Inspect saturation and queue depth, compare the latest deployment, "
        "then scale or roll back."
    ),
    "errors": (
        "Group errors by signature, inspect dependency health, and roll back "
        "if correlated with deployment."
    ),
    "authentication": (
        "Check identity-provider health and signing-key changes before invalidating sessions."
    ),
    "database": (
        "Protect data integrity first: stop unsafe writes, inspect replicas, and prepare recovery."
    ),
}


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {"message": str(value)}


def _text(value: Any, *keys: str) -> str:
    payload = _mapping(value)
    for key in keys:
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return json.dumps(value, ensure_ascii=False)


def prepare_faq(value: Any, context: Any | None) -> PreparedPrompt:
    question = _text(value, "question", "message")
    terms = {term.strip("?.,!").casefold() for term in question.split() if len(term) > 2}
    matches = [
        article
        for article in FAQ_KNOWLEDGE
        if terms.intersection(article["id"].split("-"))
        or any(term in article["text"].casefold() for term in terms)
    ][:3]
    retrieved = matches or []
    prompt = (
        f"Customer question:\n{question}\n\n"
        f"Retrieved knowledge:\n{json.dumps(retrieved, ensure_ascii=False)}\n\n"
        "Answer the question using only the retrieved knowledge. If the knowledge does not contain "
        "the answer, say that you do not know and recommend human support. Cite article IDs in "
        "square brackets."
    )
    return PreparedPrompt(
        prompt=prompt,
        spans=[
            tool_span(
                "search_knowledge_base",
                {"question": question},
                {"articles": retrieved, "match_count": len(retrieved)},
            )
        ],
    )


def prepare_research(value: Any, context: Any | None) -> PreparedPrompt:
    question = _text(value, "question", "topic", "message")
    prompt = (
        f"Research question:\n{question}\n\n"
        "Use web search to find current, credible sources. Produce a concise synthesis, "
        "distinguish facts from inference, and include source links. Do not invent citations."
    )
    return PreparedPrompt(
        prompt=prompt,
        spans=[
            tool_span(
                "openai_web_search",
                {"query": question},
                {"execution": "delegated_to_openai_responses_api"},
            )
        ],
    )


def prepare_data_analyst(value: Any, context: Any | None) -> PreparedPrompt:
    payload = _mapping(value)
    question = str(payload.get("question") or "Summarize the most important patterns.")
    raw_records = payload.get("records", [])
    records = raw_records[:100] if isinstance(raw_records, list) else []
    numeric: dict[str, list[float]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        for key, item in record.items():
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                numeric.setdefault(str(key), []).append(float(item))
    summary = {
        "record_count": len(records),
        "numeric_fields": {
            key: {"minimum": min(values), "maximum": max(values), "average": mean(values)}
            for key, values in numeric.items()
        },
    }
    prompt = (
        f"Analysis question:\n{question}\n\n"
        f"Computed dataset profile:\n{json.dumps(summary, ensure_ascii=False)}\n\n"
        f"Records (maximum 100):\n{json.dumps(records, ensure_ascii=False)}\n\n"
        "Answer with evidence from the supplied data. State limitations and do not claim causation "
        "from correlation."
    )
    return PreparedPrompt(
        prompt=prompt,
        spans=[tool_span("profile_records", {"record_count": len(records)}, summary)],
    )


def prepare_travel(value: Any, context: Any | None) -> PreparedPrompt:
    payload = _mapping(value)
    request = {
        "origin": payload.get("origin"),
        "destination": payload.get("destination"),
        "dates": payload.get("dates"),
        "nights": payload.get("nights"),
        "budget": payload.get("budget"),
        "preferences": payload.get("preferences", []),
    }
    prompt = (
        f"Trip request:\n{json.dumps(request, ensure_ascii=False)}\n\n"
        "Use web search for current destination, transport, and safety information. "
        "Create a practical itinerary within the stated constraints. Treat prices and "
        "availability as estimates, cite sources, and tell the traveler to verify before booking."
    )
    return PreparedPrompt(
        prompt=prompt,
        spans=[
            tool_span(
                "search_travel_information",
                request,
                {"execution": "delegated_to_openai_web_search"},
            )
        ],
    )


def prepare_incident(value: Any, context: Any | None) -> PreparedPrompt:
    payload = _mapping(value)
    signal = str(payload.get("signal") or payload.get("alert_type") or "errors").casefold()
    runbook_key = next((key for key in RUNBOOKS if key in signal), "errors")
    service_snapshot = {
        "service": payload.get("service", "unknown"),
        "severity": payload.get("severity", "unknown"),
        "signal": signal,
        "metrics": payload.get("metrics", {}),
        "recent_change": payload.get("recent_change"),
    }
    runbook = RUNBOOKS[runbook_key]
    prompt = (
        f"Incident snapshot:\n{json.dumps(service_snapshot, ensure_ascii=False)}\n\n"
        f"Relevant runbook:\n{runbook}\n\n"
        "Produce a cautious incident assessment with likely hypotheses, immediate safe actions, "
        "verification steps, and escalation criteria. Never claim that a destructive action "
        "was executed."
    )
    return PreparedPrompt(
        prompt=prompt,
        spans=[
            tool_span(
                "fetch_service_health", {"service": service_snapshot["service"]}, service_snapshot
            ),
            tool_span("lookup_runbook", {"signal": signal}, {"key": runbook_key, "text": runbook}),
        ],
    )


FAQ_AGENT = AgentSpec(
    name="faq-agent",
    title="Real grounded FAQ agent",
    version="faq-v2-real",
    instructions=(
        "You are a customer-support knowledge agent. Follow the supplied knowledge exactly, "
        "keep the answer short, and never fabricate company policy."
    ),
    prepare=prepare_faq,
)

RESEARCH_AGENT = AgentSpec(
    name="research-agent",
    title="Real web research agent",
    version="research-v3-real",
    instructions=(
        "You are a careful research analyst. Search before answering, prioritize primary sources, "
        "and clearly label uncertainty and inference."
    ),
    prepare=prepare_research,
    web_search=True,
)

DATA_ANALYST_AGENT = AgentSpec(
    name="data-analyst-agent",
    title="Real data analyst agent",
    version="data-analyst-v1-real",
    instructions=(
        "You are a data analyst. Base every conclusion on the supplied records and computed "
        "profile, show the relevant figures, and state data-quality limitations."
    ),
    prepare=prepare_data_analyst,
)

TRAVEL_AGENT = AgentSpec(
    name="travel-planner-agent",
    title="Real travel planning agent",
    version="travel-v2-real",
    instructions=(
        "You are a travel-planning agent. Respect constraints, use current sources, avoid "
        "guarantees about price or availability, and surface safety or visa uncertainty."
    ),
    prepare=prepare_travel,
    web_search=True,
)

INCIDENT_AGENT = AgentSpec(
    name="incident-triage-agent",
    title="Real incident triage agent",
    version="incident-v2-real",
    instructions=(
        "You are an incident commander assistant. Protect availability and data integrity, "
        "distinguish observations from hypotheses, and require human confirmation for "
        "destructive actions."
    ),
    prepare=prepare_incident,
)

ALL_AGENTS = [FAQ_AGENT, RESEARCH_AGENT, DATA_ANALYST_AGENT, TRAVEL_AGENT, INCIDENT_AGENT]
