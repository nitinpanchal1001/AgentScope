import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvaluationType(enum.StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    CONTAINS = "CONTAINS"
    REGEX = "REGEX"
    JSON_SCHEMA = "JSON_SCHEMA"
    LATENCY_THRESHOLD = "LATENCY_THRESHOLD"
    COST_THRESHOLD = "COST_THRESHOLD"
    REQUIRED_TOOL = "REQUIRED_TOOL"
    FORBIDDEN_TOOL = "FORBIDDEN_TOOL"
    TOOL_ARGUMENTS = "TOOL_ARGUMENTS"
    CITATION_PRESENCE = "CITATION_PRESENCE"
    SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
    CORRECTNESS = "CORRECTNESS"
    RELEVANCE = "RELEVANCE"
    FAITHFULNESS = "FAITHFULNESS"
    COMPLETENESS = "COMPLETENESS"
    HALLUCINATION = "HALLUCINATION"
    INSTRUCTION_FOLLOWING = "INSTRUCTION_FOLLOWING"
    TOOL_SELECTION = "TOOL_SELECTION"
    CUSTOM_RUBRIC = "CUSTOM_RUBRIC"


class EvaluationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float | None = Field(default=None, ge=0, le=1)
    passed: bool
    label: str = Field(min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=8000)
    evidence: list[Any] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=1)
    passed: bool
    label: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=8000)
    evidence: list[str] = Field(default_factory=list, max_length=20)
