from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from agentscope_api.models import (
    EvaluationSource,
    EvaluationStatus,
    EvaluatorType,
    TraceStatus,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

LLM_EVALUATOR_TYPES = {
    EvaluatorType.CORRECTNESS,
    EvaluatorType.RELEVANCE,
    EvaluatorType.FAITHFULNESS,
    EvaluatorType.COMPLETENESS,
    EvaluatorType.HALLUCINATION,
    EvaluatorType.INSTRUCTION_FOLLOWING,
    EvaluatorType.TOOL_SELECTION,
    EvaluatorType.CUSTOM_RUBRIC,
}


class EvaluatorVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EvaluatorType
    configuration: dict[str, Any] = Field(default_factory=dict)
    threshold: Decimal = Field(default=Decimal("0.8"), ge=0, le=1, max_digits=7)
    provider: Annotated[str | None, StringConstraints(max_length=100)] = None
    model: Annotated[str | None, StringConstraints(max_length=160)] = None
    rubric: Annotated[str | None, StringConstraints(max_length=20_000)] = None

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> "EvaluatorVersionCreate":
        if self.type in LLM_EVALUATOR_TYPES and not all((self.provider, self.model, self.rubric)):
            raise ValueError("LLM evaluators require provider, model, and rubric")
        if self.type in LLM_EVALUATOR_TYPES:
            external_fields = self.configuration.get("external_fields")
            allowed = {"input", "output", "expected_output", "context", "trace"}
            if not isinstance(external_fields, list) or not external_fields:
                raise ValueError("LLM evaluators require explicit external_fields")
            if any(field not in allowed for field in external_fields):
                raise ValueError("LLM evaluator external_fields contains an unsupported field")
        if self.type is EvaluatorType.SEMANTIC_SIMILARITY and not self.model:
            raise ValueError("Semantic similarity evaluators require an embedding model")
        return self


class EvaluatorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Annotated[str | None, StringConstraints(max_length=2000)] = None
    version: EvaluatorVersionCreate


class EvaluatorVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evaluator_id: UUID
    version: int
    type: EvaluatorType
    configuration: dict[str, Any]
    threshold: Decimal
    provider: str | None
    model: str | None
    rubric: str | None
    created_at: datetime


class EvaluatorResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    description: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    versions: list[EvaluatorVersionResponse]


class EvaluatorStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class EvaluationBindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_id: UUID
    evaluator_version_id: UUID
    sample_rate: Decimal = Field(default=Decimal("1"), ge=0, le=1, max_digits=7)
    threshold: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7)
    filters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class EvaluationBindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7)
    threshold: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7)
    filters: dict[str, Any] | None = None
    enabled: bool | None = None


class EvaluationBindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    environment_id: UUID
    evaluator_version_id: UUID
    enabled: bool
    sample_rate: Decimal
    threshold: Decimal | None
    filters: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluator_version_ids: list[UUID] = Field(min_length=1, max_length=50)


class EvaluationResultResponse(BaseModel):
    id: UUID
    trace_id: UUID
    evaluator_id: UUID
    evaluator_name: str
    evaluator_version_id: UUID
    evaluator_version: int
    evaluator_type: EvaluatorType
    source: EvaluationSource
    status: EvaluationStatus
    threshold: Decimal
    score: Decimal | None
    passed: bool | None
    label: str | None
    reason: str | None
    evidence: list[Any]
    metadata: dict[str, Any]
    error_type: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class WorkerEvaluationPayload(BaseModel):
    result_id: UUID
    status: EvaluationStatus
    evaluator_type: EvaluatorType
    input: Any | None
    output: Any | None
    expected_output: Any | None
    context: Any | None
    trace: dict[str, Any]
    configuration: dict[str, Any]
    threshold: Decimal
    provider: str | None
    model: str | None
    rubric: str | None


class WorkerEvaluationCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvaluationStatus
    score: Decimal | None = Field(default=None, ge=0, le=1)
    passed: bool | None = None
    label: Annotated[str | None, StringConstraints(max_length=80)] = None
    reason: Annotated[str | None, StringConstraints(max_length=20_000)] = None
    evidence: list[Any] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_type: Annotated[str | None, StringConstraints(max_length=120)] = None
    error_message: Annotated[str | None, StringConstraints(max_length=8000)] = None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "WorkerEvaluationCompletion":
        if self.status not in {EvaluationStatus.SUCCESS, EvaluationStatus.FAILED}:
            raise ValueError("Completion status must be SUCCESS or FAILED")
        if self.status is EvaluationStatus.SUCCESS and (
            self.score is None or self.passed is None or self.label is None
        ):
            raise ValueError("Successful completion requires score, passed, and label")
        if self.status is EvaluationStatus.FAILED and self.error_message is None:
            raise ValueError("Failed completion requires error_message")
        return self


class EvaluationFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statuses: list[TraceStatus] | None = None
    tags_any: list[str] | None = None
    agent_versions: list[str] | None = None
