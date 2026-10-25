from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentscope_api.models import ReplayStatus, SpanType, TraceStatus
from agentscope_api.schemas.experiments import ExperimentAgentSpan, HttpAgentConfiguration


class ReplayOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Annotated[str | None, StringConstraints(max_length=160)] = None
    prompt_version: Annotated[str | None, StringConstraints(max_length=160)] = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    agent_version: Annotated[str | None, StringConstraints(max_length=120)] = None
    parameters: dict[str, Any] | None = None


class ReplayCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: HttpAgentConfiguration
    overrides: ReplayOverrides = Field(default_factory=ReplayOverrides)


class ReplayResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    environment_id: UUID
    original_trace_id: UUID
    replay_trace_id: UUID | None
    status: ReplayStatus
    agent: HttpAgentConfiguration
    overrides: ReplayOverrides
    effective_configuration: dict[str, Any]
    error_type: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class WorkerReplayPayload(BaseModel):
    replay_id: UUID
    status: ReplayStatus
    endpoint: str
    timeout_seconds: int
    headers_from_env: dict[str, str]
    request: dict[str, Any]
    evaluation_result_ids: list[UUID] = Field(default_factory=list)


class WorkerReplayCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["SUCCESS", "FAILED"]
    output: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    spans: list[ExperimentAgentSpan] = Field(default_factory=list, max_length=1000)
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_cost: Decimal = Field(default=Decimal("0"), ge=0)
    error_type: Annotated[str | None, StringConstraints(max_length=120)] = None
    error_message: Annotated[str | None, StringConstraints(max_length=8000)] = None


class WorkerReplayCompletionResponse(BaseModel):
    status: ReplayStatus
    replay_trace_id: UUID | None
    evaluation_result_ids: list[UUID]


class ReplaySpanStructure(BaseModel):
    ordinal: int
    parent_ordinal: int | None
    type: SpanType
    name: str
    status: TraceStatus


class ReplaySnapshot(BaseModel):
    trace_id: UUID
    output: Any | None
    evaluation_score: Decimal | None
    latency_ms: int | None
    total_cost: Decimal
    total_tokens: int
    tool_sequence: list[str]
    span_structure: list[ReplaySpanStructure]


class ReplayComparison(BaseModel):
    replay_id: UUID
    original: ReplaySnapshot
    replay: ReplaySnapshot
    differences: dict[str, Any]
