from pydantic import BaseModel


class RetentionProjectResult(BaseModel):
    project_id: str
    deleted_traces: int
    skipped: bool = False
    reason: str | None = None


class RetentionRunResponse(BaseModel):
    projects: list[RetentionProjectResult]
    deleted_traces: int
