from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from agentscope_api.api.dependencies import ProjectAccessDependency, SessionDependency
from agentscope_api.repositories.projects import ProjectRepository
from agentscope_api.schemas.analytics import AnalyticsResponse
from agentscope_api.services.analytics import AnalyticsService, default_analytics_window
from agentscope_api.services.authorization import Permission, require_permission

router = APIRouter(tags=["Analytics"])


@router.get("/projects/{project_id}/analytics", response_model=AnalyticsResponse)
async def get_project_analytics(
    project_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    environment_id: UUID | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    bucket: Literal["auto", "5m", "1h", "1d"] = Query(default="auto"),
) -> AnalyticsResponse:
    require_permission(access.membership.role, Permission.ANALYTICS_READ)
    if environment_id is not None:
        environment = await ProjectRepository(session).get_environment(project_id, environment_id)
        if environment is None:
            from agentscope_api.core.exceptions import NotFoundError

            raise NotFoundError("Environment")
    default_start, default_end = default_analytics_window()
    return await AnalyticsService(session).get_project_analytics(
        project_id=project_id,
        environment_id=environment_id,
        started_after=started_after or default_start,
        started_before=started_before or default_end,
        bucket=bucket,
    )
