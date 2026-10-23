from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import ApiKey, Environment, Membership, Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def slug_exists(self, organization_id: UUID, slug: str) -> bool:
        return (
            await self.session.scalar(
                select(Project.id).where(
                    Project.organization_id == organization_id, Project.slug == slug
                )
            )
        ) is not None

    def add_project(self, project: Project) -> None:
        self.session.add(project)

    def add_environments(self, environments: list[Environment]) -> None:
        self.session.add_all(environments)

    async def list_for_organization(self, organization_id: UUID, user_id: UUID) -> list[Project]:
        rows = await self.session.scalars(
            select(Project)
            .join(Membership, Membership.organization_id == Project.organization_id)
            .where(Project.organization_id == organization_id, Membership.user_id == user_id)
            .order_by(Project.name)
        )
        return list(rows)

    async def get_scoped(
        self, project_id: UUID, user_id: UUID
    ) -> tuple[Project, Membership] | None:
        row = await self.session.execute(
            select(Project, Membership)
            .join(Membership, Membership.organization_id == Project.organization_id)
            .where(Project.id == project_id, Membership.user_id == user_id)
        )
        result = row.one_or_none()
        if result is None:
            return None
        project, membership = result
        return project, membership

    async def list_environments(self, project_id: UUID) -> list[Environment]:
        rows = await self.session.scalars(
            select(Environment)
            .where(Environment.project_id == project_id)
            .order_by(Environment.name)
        )
        return list(rows)

    async def get_environment(self, project_id: UUID, environment_id: UUID) -> Environment | None:
        return await self.session.scalar(
            select(Environment).where(
                Environment.id == environment_id, Environment.project_id == project_id
            )
        )

    def add_api_key(self, api_key: ApiKey) -> None:
        self.session.add(api_key)

    async def list_api_keys(self, project_id: UUID) -> list[ApiKey]:
        rows = await self.session.scalars(
            select(ApiKey).where(ApiKey.project_id == project_id).order_by(ApiKey.created_at.desc())
        )
        return list(rows)

    async def get_api_key(self, project_id: UUID, api_key_id: UUID) -> ApiKey | None:
        return await self.session.scalar(
            select(ApiKey)
            .where(ApiKey.id == api_key_id, ApiKey.project_id == project_id)
            .with_for_update()
        )

    async def get_active_api_key_by_hash(self, key_hash: str) -> tuple[ApiKey, Project] | None:
        row = await self.session.execute(
            select(ApiKey, Project)
            .join(Project, Project.id == ApiKey.project_id)
            .where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        )
        return row.one_or_none()
