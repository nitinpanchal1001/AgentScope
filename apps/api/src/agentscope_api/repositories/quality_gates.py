from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import (
    DatasetVersion,
    Experiment,
    ExperimentBaseline,
    QualityGate,
    QualityGateResult,
)


class QualityGateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def experiment_with_dataset(
        self, experiment_id: UUID, project_id: UUID
    ) -> tuple[Experiment, DatasetVersion] | None:
        row = await self.session.execute(
            select(Experiment, DatasetVersion)
            .join(DatasetVersion, DatasetVersion.id == Experiment.dataset_version_id)
            .where(Experiment.id == experiment_id, Experiment.project_id == project_id)
        )
        return row.one_or_none()

    async def baseline(self, dataset_id: UUID, project_id: UUID) -> ExperimentBaseline | None:
        return await self.session.scalar(
            select(ExperimentBaseline).where(
                ExperimentBaseline.dataset_id == dataset_id,
                ExperimentBaseline.project_id == project_id,
            )
        )

    async def list_gates(self, project_id: UUID) -> list[QualityGate]:
        values = await self.session.scalars(
            select(QualityGate)
            .where(QualityGate.project_id == project_id)
            .order_by(QualityGate.created_at.desc())
        )
        return list(values)

    async def gate(self, gate_id: UUID, project_id: UUID) -> QualityGate | None:
        return await self.session.scalar(
            select(QualityGate).where(
                QualityGate.id == gate_id, QualityGate.project_id == project_id
            )
        )

    async def results(self, candidate_id: UUID, project_id: UUID) -> list[QualityGateResult]:
        values = await self.session.scalars(
            select(QualityGateResult)
            .where(
                QualityGateResult.candidate_experiment_id == candidate_id,
                QualityGateResult.project_id == project_id,
            )
            .order_by(QualityGateResult.evaluated_at.desc())
        )
        return list(values)
