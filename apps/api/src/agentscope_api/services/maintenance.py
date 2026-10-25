from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.config import Settings
from agentscope_api.models import FailureRecord, IngestionEvent, Project, Trace, TraceReplay
from agentscope_api.schemas.maintenance import RetentionProjectResult, RetentionRunResponse
from agentscope_api.services.failure_intelligence import QdrantFailureIndex


class MaintenanceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.index = QdrantFailureIndex(settings.qdrant_url, settings.qdrant_api_key)

    async def expire_telemetry(self, now: datetime | None = None) -> RetentionRunResponse:
        current = now or datetime.now(UTC)
        projects = list(await self.session.scalars(select(Project).order_by(Project.id)))
        results: list[RetentionProjectResult] = []
        for project in projects:
            cutoff = current - timedelta(days=project.retention_days)
            trace_ids = select(Trace.id).where(
                Trace.project_id == project.id, Trace.created_at < cutoff
            )
            count = int(
                await self.session.scalar(
                    select(func.count(Trace.id)).where(
                        Trace.project_id == project.id, Trace.created_at < cutoff
                    )
                )
                or 0
            )
            if count == 0:
                results.append(RetentionProjectResult(project_id=str(project.id), deleted_traces=0))
                continue
            vector_ids = list(
                await self.session.scalars(
                    select(FailureRecord.vector_point_id).where(
                        FailureRecord.trace_id.in_(trace_ids)
                    )
                )
            )
            try:
                await self.index.delete_points(vector_ids)
            except httpx.HTTPError as error:
                results.append(
                    RetentionProjectResult(
                        project_id=str(project.id),
                        deleted_traces=0,
                        skipped=True,
                        reason=f"vector index unavailable: {type(error).__name__}",
                    )
                )
                continue
            await self.session.execute(
                delete(TraceReplay).where(
                    TraceReplay.project_id == project.id,
                    or_(
                        TraceReplay.original_trace_id.in_(trace_ids),
                        TraceReplay.replay_trace_id.in_(trace_ids),
                    ),
                )
            )
            await self.session.execute(delete(Trace).where(Trace.id.in_(trace_ids)))
            await self.session.execute(
                delete(IngestionEvent).where(
                    IngestionEvent.project_id == project.id,
                    IngestionEvent.received_at < cutoff,
                )
            )
            await self.session.commit()
            results.append(RetentionProjectResult(project_id=str(project.id), deleted_traces=count))
        return RetentionRunResponse(
            projects=results,
            deleted_traces=sum(value.deleted_traces for value in results),
        )
