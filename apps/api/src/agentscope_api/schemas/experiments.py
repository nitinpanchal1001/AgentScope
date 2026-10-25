from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from agentscope_api.models import ExperimentRunStatus, ExperimentStatus, SpanType, TraceStatus

ExperimentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]
HeaderName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$",
    ),
]
EnvironmentVariableName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Z_][A-Z0-9_]*$",
    ),
]


class HttpAgentConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["http"] = "http"
    endpoint: AnyHttpUrl
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    headers_from_env: dict[HeaderName, EnvironmentVariableName] = Field(
        default_factory=dict, max_length=20
    )
    provider: Annotated[str | None, StringConstraints(max_length=100)] = None
    model: Annotated[str | None, StringConstraints(max_length=160)] = None
    prompt_version: Annotated[str | None, StringConstraints(max_length=160)] = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint")
    @classmethod
    def endpoint_has_no_inline_credentials(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("endpoint credentials must use headers_from_env")
        return value


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ExperimentName
    description: Annotated[str | None, StringConstraints(max_length=4000)] = None
    dataset_version_id: UUID
    environment_id: UUID
    agent: HttpAgentConfiguration
    evaluator_version_ids: list[UUID] = Field(min_length=1, max_length=50)
    max_concurrency: int = Field(default=5, ge=1, le=100)


class ExperimentResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    environment_id: UUID
    dataset_version_id: UUID
    dataset_name: str
    dataset_version: int
    name: str
    description: str | None
    status: ExperimentStatus
    agent: HttpAgentConfiguration
    evaluator_version_ids: list[UUID]
    max_concurrency: int
    total_cases: int
    completed_cases: int
    passed_cases: int
    failed_cases: int
    metrics: dict[str, Any]
    cancel_requested: bool
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ExperimentRunResponse(BaseModel):
    id: UUID
    experiment_id: UUID
    dataset_item_id: UUID
    trace_id: UUID | None
    ordinal: int
    status: ExperimentRunStatus
    input: Any
    expected_output: Any | None
    expected_tools: list[str]
    output: Any | None
    latency_ms: int | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost: Decimal
    evaluation_score: Decimal | None
    passed: bool | None
    error_type: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class ExperimentRunPage(BaseModel):
    items: list[ExperimentRunResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ExperimentAgentSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SpanType = SpanType.CUSTOM
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    provider: Annotated[str | None, StringConstraints(max_length=100)] = None
    model: Annotated[str | None, StringConstraints(max_length=160)] = None
    input: Any | None = None
    output: Any | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    status: TraceStatus = TraceStatus.SUCCESS
    error_type: Annotated[str | None, StringConstraints(max_length=120)] = None
    error_message: Annotated[str | None, StringConstraints(max_length=8000)] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=50
    )


class WorkerExperimentRunPayload(BaseModel):
    run_id: UUID
    status: ExperimentRunStatus
    endpoint: AnyHttpUrl
    timeout_seconds: int
    headers_from_env: dict[str, str]
    request: dict[str, Any]


class WorkerExperimentRunCompletion(BaseModel):
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


class WorkerExperimentRunCompletionResponse(BaseModel):
    evaluation_result_ids: list[UUID]
    next_run_ids: list[UUID]
