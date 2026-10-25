from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import Dataset, DatasetItem, DatasetVersion


class DatasetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_datasets(self, project_id: UUID) -> list[tuple[Dataset, list[DatasetVersion]]]:
        datasets = list(
            await self.session.scalars(
                select(Dataset)
                .where(Dataset.project_id == project_id)
                .order_by(Dataset.updated_at.desc(), Dataset.id)
            )
        )
        if not datasets:
            return []
        versions = list(
            await self.session.scalars(
                select(DatasetVersion)
                .where(DatasetVersion.dataset_id.in_([dataset.id for dataset in datasets]))
                .order_by(DatasetVersion.dataset_id, DatasetVersion.version.desc())
            )
        )
        by_dataset: dict[UUID, list[DatasetVersion]] = {}
        for version in versions:
            by_dataset.setdefault(version.dataset_id, []).append(version)
        return [(dataset, by_dataset.get(dataset.id, [])) for dataset in datasets]

    async def get_dataset(self, dataset_id: UUID, project_id: UUID) -> Dataset | None:
        return await self.session.scalar(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
        )

    async def lock_dataset(self, dataset_id: UUID, project_id: UUID) -> Dataset | None:
        return await self.session.scalar(
            select(Dataset)
            .where(Dataset.id == dataset_id, Dataset.project_id == project_id)
            .with_for_update()
        )

    async def list_versions(self, dataset_id: UUID) -> list[DatasetVersion]:
        versions = await self.session.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version.desc())
        )
        return list(versions)

    async def get_version(self, dataset_id: UUID, version_number: int) -> DatasetVersion | None:
        return await self.session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.version == version_number,
            )
        )

    async def find_content_hash(self, dataset_id: UUID, content_hash: str) -> DatasetVersion | None:
        return await self.session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.content_hash == content_hash,
            )
        )

    async def next_version(self, dataset_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.max(DatasetVersion.version)).where(DatasetVersion.dataset_id == dataset_id)
        )
        return int(latest or 0) + 1

    async def list_items(
        self, dataset_version_id: UUID, *, offset: int = 0, limit: int | None = None
    ) -> list[DatasetItem]:
        statement = (
            select(DatasetItem)
            .where(DatasetItem.dataset_version_id == dataset_version_id)
            .order_by(DatasetItem.ordinal)
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)
        items = await self.session.scalars(statement)
        return list(items)

    def add(self, entity: Dataset | DatasetVersion | DatasetItem) -> None:
        self.session.add(entity)

    def add_items(self, items: list[DatasetItem]) -> None:
        self.session.add_all(items)
