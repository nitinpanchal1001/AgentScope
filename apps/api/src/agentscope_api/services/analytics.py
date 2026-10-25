from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.exceptions import AppError
from agentscope_api.repositories.analytics import AnalyticsRepository
from agentscope_api.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsSummary,
    UsageBreakdown,
)

Bucket = Literal["auto", "5m", "1h", "1d"]
BUCKET_SECONDS = {"5m": 300, "1h": 3600, "1d": 86400}
MAX_ANALYTICS_RANGE = timedelta(days=90)


def select_bucket(started_after: datetime, started_before: datetime, requested: Bucket) -> str:
    if requested != "auto":
        return requested
    duration = started_before - started_after
    if duration <= timedelta(hours=6):
        return "5m"
    if duration <= timedelta(days=7):
        return "1h"
    return "1d"


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = AnalyticsRepository(session)

    async def get_project_analytics(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        started_after: datetime,
        started_before: datetime,
        bucket: Bucket,
    ) -> AnalyticsResponse:
        if started_after.tzinfo is None:
            started_after = started_after.replace(tzinfo=UTC)
        if started_before.tzinfo is None:
            started_before = started_before.replace(tzinfo=UTC)
        if started_before <= started_after:
            raise AppError(
                "INVALID_ANALYTICS_RANGE",
                "started_before must be later than started_after",
                status_code=422,
            )
        if started_before - started_after > MAX_ANALYTICS_RANGE:
            raise AppError(
                "ANALYTICS_RANGE_TOO_LARGE",
                "Analytics queries are limited to 90 days",
                status_code=422,
            )
        selected_bucket = select_bucket(started_after, started_before, bucket)
        summary = await self.repository.summary(
            project_id=project_id,
            environment_id=environment_id,
            started_after=started_after,
            started_before=started_before,
        )
        total = summary["total_traces"]
        summary["success_rate"] = (
            round(summary["successful_traces"] / total * 100, 2) if total else 0.0
        )
        summary["error_rate"] = round(summary["error_traces"] / total * 100, 2) if total else 0.0
        timeseries = await self.repository.timeseries(
            project_id=project_id,
            environment_id=environment_id,
            started_after=started_after,
            started_before=started_before,
            bucket_seconds=BUCKET_SECONDS[selected_bucket],
        )
        models = await self.repository.span_breakdown(
            project_id=project_id,
            environment_id=environment_id,
            started_after=started_after,
            started_before=started_before,
            dimension="model",
        )
        providers = await self.repository.span_breakdown(
            project_id=project_id,
            environment_id=environment_id,
            started_after=started_after,
            started_before=started_before,
            dimension="provider",
        )
        tools = await self.repository.span_breakdown(
            project_id=project_id,
            environment_id=environment_id,
            started_after=started_after,
            started_before=started_before,
            dimension="tool",
        )
        agents = await self.repository.trace_breakdown(
            project_id=project_id,
            environment_id=environment_id,
            started_after=started_after,
            started_before=started_before,
            dimension="agent",
        )
        failures = await self.repository.trace_breakdown(
            project_id=project_id,
            environment_id=environment_id,
            started_after=started_after,
            started_before=started_before,
            dimension="failure",
        )
        return AnalyticsResponse(
            started_after=started_after,
            started_before=started_before,
            bucket=selected_bucket,
            summary=AnalyticsSummary(**summary),
            timeseries=timeseries,
            models=[UsageBreakdown(**item) for item in models],
            providers=[UsageBreakdown(**item) for item in providers],
            tools=[UsageBreakdown(**item) for item in tools],
            agents=[UsageBreakdown(**item) for item in agents],
            failure_types=[UsageBreakdown(**item) for item in failures],
        )


def default_analytics_window() -> tuple[datetime, datetime]:
    ended_at = datetime.now(UTC)
    return ended_at - timedelta(hours=24), ended_at
