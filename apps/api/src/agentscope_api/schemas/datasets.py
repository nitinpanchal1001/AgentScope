from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DatasetName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class DatasetCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Any
    expected_output: Any | None = None
    expected_tools: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    ] = Field(default_factory=list, max_length=100)
    context: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DatasetName
    description: Annotated[str | None, StringConstraints(max_length=4000)] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    items: list[DatasetCase] = Field(min_length=1, max_length=10_000)


class DatasetVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, Any] = Field(default_factory=dict)
    items: list[DatasetCase] = Field(min_length=1, max_length=10_000)


class DatasetAppendCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: DatasetCase
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    version: int
    content_hash: str
    item_count: int
    metadata: dict[str, Any]
    created_at: datetime


class DatasetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: DatasetVersionSummary
    versions: list[DatasetVersionSummary]


class DatasetItemResponse(BaseModel):
    id: UUID
    dataset_version_id: UUID
    ordinal: int
    input: Any
    expected_output: Any | None
    expected_tools: list[str]
    context: Any | None
    metadata: dict[str, Any]


class PageMetadata(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class DatasetVersionPage(BaseModel):
    dataset_id: UUID
    dataset_name: str
    version: DatasetVersionSummary
    items: list[DatasetItemResponse]
    pagination: PageMetadata


DatasetImportFormat = Literal["json", "jsonl", "csv"]
