from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentscope_api.models import FailureType, SpanType, TelemetryEventType, TraceStatus

ExternalId = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class SdkDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    version: Annotated[str, StringConstraints(min_length=1, max_length=40)]


class TelemetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, StringConstraints(max_length=200)] = None
    span_type: SpanType | None = None
    status: TraceStatus | None = None
    input: Any | None = None
    output: Any | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    provider: Annotated[str | None, StringConstraints(max_length=100)] = None
    model: Annotated[str | None, StringConstraints(max_length=160)] = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    agent_version: Annotated[str | None, StringConstraints(max_length=120)] = None
    session_id: Annotated[str | None, StringConstraints(max_length=200)] = None
    user_identifier: Annotated[str | None, StringConstraints(max_length=200)] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=50
    )
    error_type: FailureType | None = None
    error_message: Annotated[str | None, StringConstraints(max_length=8000)] = None


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    timestamp: datetime
    type: TelemetryEventType
    trace_id: ExternalId
    span_id: ExternalId | None = None
    parent_span_id: ExternalId | None = None
    payload: TelemetryPayload


class IngestionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sdk: SdkDescriptor
    events: list[TelemetryEvent] = Field(min_length=1)


class IngestionResponse(BaseModel):
    accepted: int
    duplicates: int


class SpanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_span_id: str
    trace_id: UUID
    parent_span_id: UUID | None
    type: SpanType
    name: str
    provider: str | None
    model: str | None
    input: Any | None
    output: Any | None
    started_at: datetime
    ended_at: datetime | None
    latency_ms: int | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: Decimal
    status: TraceStatus
    error_type: FailureType | None
    error_message: str | None
    metadata: dict[str, Any]
    tags: list[str]


class TraceSummary(BaseModel):
    id: UUID
    external_trace_id: str
    project_id: UUID
    environment_id: UUID
    environment: str
    name: str
    status: TraceStatus
    started_at: datetime
    ended_at: datetime | None
    latency_ms: int | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost: Decimal
    agent_version: str | None
    error_type: FailureType | None
    created_at: datetime


class TraceDetail(TraceSummary):
    input: Any | None
    output: Any | None
    session_id: str | None
    user_identifier: str | None
    metadata: dict[str, Any]
    tags: list[str]
    error_message: str | None
    spans: list[SpanResponse]


class TracePage(BaseModel):
    items: list[TraceSummary]
    next_cursor: str | None
