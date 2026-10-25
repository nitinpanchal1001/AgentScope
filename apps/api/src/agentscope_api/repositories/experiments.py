from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    EvaluationResult,
    Evaluator,
    EvaluatorVersion,
    Experiment,
    ExperimentEvaluatorVersion,
    ExperimentRun,
    ExperimentRunStatus,
)


class ExperimentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_experiments(
        self, project_id: UUID
    ) -> list[tuple[Experiment, DatasetVersion, Dataset, list[UUID]]]:
        rows = await self.session.execute(
            select(Experiment, DatasetVersion, Dataset)
            .join(DatasetVersion, DatasetVersion.id == Experiment.dataset_version_id)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Experiment.project_id == project_id)
            .order_by(Experiment.created_at.desc(), Experiment.id.desc())
        )
        values = list(rows.all())
        evaluator_ids = await self._evaluator_ids([row[0].id for row in values])
        return [(row[0], row[1], row[2], evaluator_ids.get(row[0].id, [])) for row in values]

    async def get_experiment(
        self, experiment_id: UUID, project_id: UUID
    ) -> tuple[Experiment, DatasetVersion, Dataset, list[UUID]] | None:
        row = await self.session.execute(
            select(Experiment, DatasetVersion, Dataset)
            .join(DatasetVersion, DatasetVersion.id == Experiment.dataset_version_id)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Experiment.id == experiment_id, Experiment.project_id == project_id)
        )
        value = row.one_or_none()
        if value is None:
            return None
        evaluator_ids = await self._evaluator_ids([experiment_id])
        return value[0], value[1], value[2], evaluator_ids.get(experiment_id, [])

    async def lock_experiment(self, experiment_id: UUID) -> Experiment | None:
        return await self.session.scalar(
            select(Experiment).where(Experiment.id == experiment_id).with_for_update()
        )

    async def dataset_version(
        self, dataset_version_id: UUID, project_id: UUID
    ) -> tuple[DatasetVersion, Dataset] | None:
        row = await self.session.execute(
            select(DatasetVersion, Dataset)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(
                DatasetVersion.id == dataset_version_id,
                Dataset.project_id == project_id,
            )
        )
        return row.one_or_none()

    async def dataset_items(self, dataset_version_id: UUID) -> list[DatasetItem]:
        values = await self.session.scalars(
            select(DatasetItem)
            .where(DatasetItem.dataset_version_id == dataset_version_id)
            .order_by(DatasetItem.ordinal)
        )
        return list(values)

    async def evaluator_versions_exist(
        self, evaluator_version_ids: list[UUID], project_id: UUID
    ) -> bool:
        count = await self.session.scalar(
            select(func.count(EvaluatorVersion.id))
            .join(Evaluator, Evaluator.id == EvaluatorVersion.evaluator_id)
            .where(
                EvaluatorVersion.id.in_(evaluator_version_ids),
                Evaluator.project_id == project_id,
            )
        )
        return int(count or 0) == len(set(evaluator_version_ids))

    async def evaluator_version_ids(self, experiment_id: UUID) -> list[UUID]:
        values = await self.session.scalars(
            select(ExperimentEvaluatorVersion.evaluator_version_id)
            .where(ExperimentEvaluatorVersion.experiment_id == experiment_id)
            .order_by(ExperimentEvaluatorVersion.evaluator_version_id)
        )
        return list(values)

    async def _evaluator_ids(self, experiment_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        if not experiment_ids:
            return {}
        rows = await self.session.execute(
            select(
                ExperimentEvaluatorVersion.experiment_id,
                ExperimentEvaluatorVersion.evaluator_version_id,
            )
            .where(ExperimentEvaluatorVersion.experiment_id.in_(experiment_ids))
            .order_by(
                ExperimentEvaluatorVersion.experiment_id,
                ExperimentEvaluatorVersion.evaluator_version_id,
            )
        )
        result: dict[UUID, list[UUID]] = {}
        for experiment_id, evaluator_id in rows.all():
            result.setdefault(experiment_id, []).append(evaluator_id)
        return result

    async def claim_pending_runs(self, experiment_id: UUID, limit: int) -> list[ExperimentRun]:
        runs = list(
            await self.session.scalars(
                select(ExperimentRun)
                .where(
                    ExperimentRun.experiment_id == experiment_id,
                    ExperimentRun.status == ExperimentRunStatus.PENDING,
                )
                .order_by(ExperimentRun.ordinal)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        return runs

    async def lock_run(self, run_id: UUID) -> ExperimentRun | None:
        return await self.session.scalar(
            select(ExperimentRun).where(ExperimentRun.id == run_id).with_for_update()
        )

    async def run_payload(
        self, run_id: UUID
    ) -> tuple[ExperimentRun, Experiment, DatasetItem] | None:
        row = await self.session.execute(
            select(ExperimentRun, Experiment, DatasetItem)
            .join(Experiment, Experiment.id == ExperimentRun.experiment_id)
            .join(DatasetItem, DatasetItem.id == ExperimentRun.dataset_item_id)
            .where(ExperimentRun.id == run_id)
            .with_for_update()
        )
        return row.one_or_none()

    async def list_runs(
        self, experiment_id: UUID, *, offset: int = 0, limit: int | None = None
    ) -> list[tuple[ExperimentRun, DatasetItem]]:
        statement = (
            select(ExperimentRun, DatasetItem)
            .join(DatasetItem, DatasetItem.id == ExperimentRun.dataset_item_id)
            .where(ExperimentRun.experiment_id == experiment_id)
            .order_by(ExperimentRun.ordinal)
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        rows = await self.session.execute(statement)
        return [(row[0], row[1]) for row in rows.all()]

    async def evaluation_results(self, run_id: UUID) -> list[EvaluationResult]:
        values = await self.session.scalars(
            select(EvaluationResult)
            .where(EvaluationResult.experiment_run_id == run_id)
            .order_by(EvaluationResult.created_at)
        )
        return list(values)

    def add_all(self, entities: Sequence[object]) -> None:
        self.session.add_all(entities)
