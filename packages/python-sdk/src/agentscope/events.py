from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def telemetry_event(
    event_type: str,
    trace_id: str,
    payload: dict[str, Any],
    *,
    span_id: str | None = None,
    parent_span_id: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "type": event_type,
        "trace_id": trace_id,
        "payload": payload,
    }
    if span_id is not None:
        event["span_id"] = span_id
    if parent_span_id is not None:
        event["parent_span_id"] = parent_span_id
    return event
