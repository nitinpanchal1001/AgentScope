from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FailureResponse(BaseModel):
    id: UUID
    project_id: UUID
    trace_id: UUID
    failure_type: str
    title: str
    document: str
    evidence: dict[str, Any]
    agent_version: str | None
    detected_at: datetime
    created_at: datetime


class FailureSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=10, ge=1, le=50)


class SimilarFailure(BaseModel):
    failure: FailureResponse
    similarity: float = Field(ge=-1, le=1)


class FailureClusterResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    description: str
    probable_cause: str | None
    suggested_action: str | None
    summary_source: str
    size: int
    failure_percentage: Decimal
    first_seen: datetime
    last_seen: datetime
    representative_failure_ids: list[UUID]
    failure_ids: list[UUID] = Field(default_factory=list)
