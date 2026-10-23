from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceContext:
    trace_id: str
    sampled: bool
    pending: list[dict[str, Any]] = field(default_factory=list)


current_trace: ContextVar[TraceContext | None] = ContextVar(
    "agentscope_current_trace", default=None
)
current_span_id: ContextVar[str | None] = ContextVar("agentscope_current_span_id", default=None)
