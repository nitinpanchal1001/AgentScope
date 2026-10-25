from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import (
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorVersion,
    ProductionEvaluationBinding,
    Span,
    Trace,
)


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_evaluators(
        self, project_id: UUID
    ) -> list[tuple[Evaluator, list[EvaluatorVersion]]]:
        evaluators = list(
            await self.session.scalars(
                select(Evaluator)
                .where(Evaluator.project_id == project_id)
                .order_by(Evaluator.created_at.desc())
            )
        )
        if not evaluators:
            return []
        versions = list(
            await self.session.scalars(
                select(EvaluatorVersion)
                .where(EvaluatorVersion.evaluator_id.in_([item.id for item in evaluators]))
                .order_by(EvaluatorVersion.evaluator_id, EvaluatorVersion.version.desc())
            )
        )
        by_evaluator: dict[UUID, list[EvaluatorVersion]] = {}
        for version in versions:
            by_evaluator.setdefault(version.evaluator_id, []).append(version)
        return [(item, by_evaluator.get(item.id, [])) for item in evaluators]

    async def get_evaluator(self, evaluator_id: UUID, project_id: UUID) -> Evaluator | None:
        return await self.session.scalar(
            select(Evaluator).where(
                Evaluator.id == evaluator_id,
                Evaluator.project_id == project_id,
            )
        )

    async def get_version(
        self, evaluator_version_id: UUID, project_id: UUID
    ) -> tuple[EvaluatorVersion, Evaluator] | None:
        row = await self.session.execute(
            select(EvaluatorVersion, Evaluator)
            .join(Evaluator, Evaluator.id == EvaluatorVersion.evaluator_id)
            .where(
                EvaluatorVersion.id == evaluator_version_id,
                Evaluator.project_id == project_id,
            )
        )
        return row.one_or_none()

    async def next_version(self, evaluator_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.max(EvaluatorVersion.version)).where(
                EvaluatorVersion.evaluator_id == evaluator_id
            )
        )
        return int(value or 0) + 1

    async def list_bindings(self, project_id: UUID) -> list[ProductionEvaluationBinding]:
        rows = await self.session.scalars(
            select(ProductionEvaluationBinding)
            .where(ProductionEvaluationBinding.project_id == project_id)
            .order_by(ProductionEvaluationBinding.created_at.desc())
        )
        return list(rows)

    async def get_binding(
        self, binding_id: UUID, project_id: UUID
    ) -> ProductionEvaluationBinding | None:
        return await self.session.scalar(
            select(ProductionEvaluationBinding).where(
                ProductionEvaluationBinding.id == binding_id,
                ProductionEvaluationBinding.project_id == project_id,
            )
        )

    async def active_bindings_for_trace(
        self, trace: Trace
    ) -> list[tuple[ProductionEvaluationBinding, EvaluatorVersion]]:
        rows = await self.session.execute(
            select(ProductionEvaluationBinding, EvaluatorVersion)
            .join(
                EvaluatorVersion,
                EvaluatorVersion.id == ProductionEvaluationBinding.evaluator_version_id,
            )
            .join(Evaluator, Evaluator.id == EvaluatorVersion.evaluator_id)
            .where(
                ProductionEvaluationBinding.project_id == trace.project_id,
                ProductionEvaluationBinding.environment_id == trace.environment_id,
                ProductionEvaluationBinding.enabled.is_(True),
                Evaluator.enabled.is_(True),
            )
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def existing_result(
        self,
        *,
        trace_id: UUID,
        evaluator_version_id: UUID,
        source: Any,
    ) -> EvaluationResult | None:
        return await self.session.scalar(
            select(EvaluationResult).where(
                EvaluationResult.trace_id == trace_id,
                EvaluationResult.evaluator_version_id == evaluator_version_id,
                EvaluationResult.source == source,
            )
        )

    async def list_results_for_trace(
        self, trace_id: UUID, project_id: UUID
    ) -> list[tuple[EvaluationResult, EvaluatorVersion, Evaluator]]:
        rows = await self.session.execute(
            select(EvaluationResult, EvaluatorVersion, Evaluator)
            .join(
                EvaluatorVersion,
                EvaluatorVersion.id == EvaluationResult.evaluator_version_id,
            )
            .join(Evaluator, Evaluator.id == EvaluatorVersion.evaluator_id)
            .where(
                EvaluationResult.trace_id == trace_id,
                EvaluationResult.project_id == project_id,
            )
            .order_by(EvaluationResult.created_at.desc())
        )
        return [(row[0], row[1], row[2]) for row in rows.all()]

    async def worker_payload(
        self, result_id: UUID
    ) -> tuple[EvaluationResult, Trace, EvaluatorVersion, list[Span]] | None:
        row = await self.session.execute(
            select(EvaluationResult, Trace, EvaluatorVersion)
            .join(Trace, Trace.id == EvaluationResult.trace_id)
            .join(
                EvaluatorVersion,
                EvaluatorVersion.id == EvaluationResult.evaluator_version_id,
            )
            .where(EvaluationResult.id == result_id)
            .with_for_update()
        )
        value = row.one_or_none()
        if value is None:
            return None
        result, trace, version = value
        spans = list(
            await self.session.scalars(
                select(Span).where(Span.trace_id == trace.id).order_by(Span.started_at, Span.id)
            )
        )
        return result, trace, version, spans

    async def refresh_trace_score(self, trace_id: UUID) -> None:
        score = await self.session.scalar(
            select(func.avg(EvaluationResult.score)).where(
                EvaluationResult.trace_id == trace_id,
                EvaluationResult.status == EvaluationStatus.SUCCESS,
                EvaluationResult.score.is_not(None),
            )
        )
        trace = await self.session.get(Trace, trace_id)
        if trace is not None:
            trace.evaluation_score = score

    def add_all(self, entities: Sequence[Any]) -> None:
        self.session.add_all(entities)
