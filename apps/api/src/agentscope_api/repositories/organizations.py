from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import Membership, Organization, User


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def slug_exists(self, slug: str) -> bool:
        return (
            await self.session.scalar(select(Organization.id).where(Organization.slug == slug))
        ) is not None

    def add(self, organization: Organization, membership: Membership) -> None:
        self.session.add_all([organization, membership])

    async def list_for_user(self, user_id: UUID) -> list[tuple[Organization, Membership]]:
        rows = await self.session.execute(
            select(Organization, Membership)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user_id)
            .order_by(Organization.name)
        )
        return [(organization, membership) for organization, membership in rows]

    async def get_membership(self, organization_id: UUID, user_id: UUID) -> Membership | None:
        return await self.session.scalar(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
            )
        )

    async def get(
        self, organization_id: UUID, user_id: UUID
    ) -> tuple[Organization, Membership] | None:
        row = await self.session.execute(
            select(Organization, Membership)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Organization.id == organization_id, Membership.user_id == user_id)
        )
        result = row.one_or_none()
        if result is None:
            return None
        organization, membership = result
        return organization, membership

    async def list_members(self, organization_id: UUID) -> list[tuple[Membership, User]]:
        rows = await self.session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == organization_id)
            .order_by(User.email)
        )
        return [(membership, user) for membership, user in rows]
