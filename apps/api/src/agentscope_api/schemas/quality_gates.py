from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentscope_api.models import QualityGateStatus

QualityMetric = Literal[
    "pass_rate",
    "average_correctness",
    "hallucination_rate",
    "tool_accuracy",
    "average_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "average_cost",
    "total_cost",
    "token_usage",
]


class QualityGateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: QualityMetric
    constraint: Literal["max_regression", "max_increase"]
    threshold: float = Field(ge=0)
    comparison: Literal["absolute", "relative"] = "absolute"
    severity: Literal["FAIL", "WARN"] = "FAIL"


class QualityGateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    description: Annotated[str | None, StringConstraints(max_length=4000)] = None
    rules: list[QualityGateRule] = Field(min_length=1, max_length=100)


class QualityGateResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    description: str | None
    rules: list[QualityGateRule]
    created_at: datetime
    updated_at: datetime


class BaselineResponse(BaseModel):
    id: UUID
    project_id: UUID
    dataset_id: UUID
    experiment_id: UUID
    experiment_name: str
    created_at: datetime
    updated_at: datetime


class MetricComparison(BaseModel):
    metric: QualityMetric
    baseline: float
    candidate: float
    absolute_delta: float
    percentage_delta: float | None
    direction: Literal["UP", "DOWN", "UNCHANGED"]
    classification: Literal["IMPROVEMENT", "REGRESSION", "UNCHANGED"]


class GateFinding(BaseModel):
    metric: QualityMetric
    message: str
    observed: float
    threshold: float
    comparison: Literal["absolute", "relative"]


class QualityGateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_experiment_id: UUID


class QualityGateResultResponse(BaseModel):
    id: UUID
    quality_gate_id: UUID
    baseline_experiment_id: UUID
    candidate_experiment_id: UUID
    status: QualityGateStatus
    comparisons: list[MetricComparison]
    violations: list[GateFinding]
    warnings: list[GateFinding]
    evaluated_at: datetime
