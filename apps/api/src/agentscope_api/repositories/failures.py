from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import (
    EvaluationResult,
    FailureCluster,
    FailureClusterMember,
    FailureRecord,
    Span,
    Trace,
)


class FailureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def trace(self, trace_id: UUID, project_id: UUID) -> Trace | None:
        return await self.session.scalar(
            select(Trace).where(Trace.id == trace_id, Trace.project_id == project_id)
        )

    async def spans(self, trace_id: UUID) -> list[Span]:
        values = await self.session.scalars(
            select(Span).where(Span.trace_id == trace_id).order_by(Span.started_at, Span.id)
        )
        return list(values)

    async def evaluations(self, trace_id: UUID) -> list[EvaluationResult]:
        values = await self.session.scalars(
            select(EvaluationResult)
            .where(EvaluationResult.trace_id == trace_id)
            .order_by(EvaluationResult.created_at)
        )
        return list(values)

    async def by_trace(self, trace_id: UUID, project_id: UUID) -> FailureRecord | None:
        return await self.session.scalar(
            select(FailureRecord).where(
                FailureRecord.trace_id == trace_id, FailureRecord.project_id == project_id
            )
        )

    async def failure(self, failure_id: UUID, project_id: UUID) -> FailureRecord | None:
        return await self.session.scalar(
            select(FailureRecord).where(
                FailureRecord.id == failure_id, FailureRecord.project_id == project_id
            )
        )

    async def failures(self, project_id: UUID) -> list[FailureRecord]:
        values = await self.session.scalars(
            select(FailureRecord)
            .where(FailureRecord.project_id == project_id)
            .order_by(FailureRecord.detected_at.desc())
        )
        return list(values)

    async def failures_by_ids(self, ids: list[UUID], project_id: UUID) -> list[FailureRecord]:
        if not ids:
            return []
        values = await self.session.scalars(
            select(FailureRecord).where(
                FailureRecord.id.in_(ids), FailureRecord.project_id == project_id
            )
        )
        by_id = {item.id: item for item in values}
        return [by_id[item] for item in ids if item in by_id]

    async def replace_clusters(self, project_id: UUID) -> None:
        await self.session.execute(
            delete(FailureCluster).where(FailureCluster.project_id == project_id)
        )

    async def clusters(self, project_id: UUID) -> list[FailureCluster]:
        values = await self.session.scalars(
            select(FailureCluster)
            .where(FailureCluster.project_id == project_id)
            .order_by(FailureCluster.size.desc(), FailureCluster.last_seen.desc())
        )
        return list(values)

    async def cluster(self, cluster_id: UUID, project_id: UUID) -> FailureCluster | None:
        return await self.session.scalar(
            select(FailureCluster).where(
                FailureCluster.id == cluster_id, FailureCluster.project_id == project_id
            )
        )

    async def cluster_failure_ids(self, cluster_id: UUID) -> list[UUID]:
        values = await self.session.scalars(
            select(FailureClusterMember.failure_id).where(
                FailureClusterMember.cluster_id == cluster_id
            )
        )
        return list(values)
