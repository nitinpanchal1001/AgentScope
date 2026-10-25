from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import EvaluationResult, Span, Trace, TraceReplay


class ReplayRepository:
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

    async def replay(self, replay_id: UUID, project_id: UUID) -> TraceReplay | None:
        return await self.session.scalar(
            select(TraceReplay).where(
                TraceReplay.id == replay_id, TraceReplay.project_id == project_id
            )
        )

    async def lock_replay(self, replay_id: UUID) -> TraceReplay | None:
        return await self.session.scalar(
            select(TraceReplay).where(TraceReplay.id == replay_id).with_for_update()
        )

    async def replay_by_trace(self, trace_id: UUID) -> TraceReplay | None:
        return await self.session.scalar(
            select(TraceReplay).where(TraceReplay.replay_trace_id == trace_id).with_for_update()
        )

    async def list_for_original(
        self, original_trace_id: UUID, project_id: UUID
    ) -> list[TraceReplay]:
        values = await self.session.scalars(
            select(TraceReplay)
            .where(
                TraceReplay.original_trace_id == original_trace_id,
                TraceReplay.project_id == project_id,
            )
            .order_by(TraceReplay.created_at.desc())
        )
        return list(values)

    async def evaluations(self, trace_id: UUID) -> list[EvaluationResult]:
        values = await self.session.scalars(
            select(EvaluationResult)
            .where(EvaluationResult.trace_id == trace_id)
            .order_by(EvaluationResult.created_at)
        )
        return list(values)
