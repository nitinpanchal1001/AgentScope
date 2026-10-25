from datetime import datetime
from uuid import UUID

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import ModelPricing


class PricingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_project(self, project_id: UUID) -> list[ModelPricing]:
        rows = await self.session.scalars(
            select(ModelPricing)
            .where(or_(ModelPricing.project_id == project_id, ModelPricing.project_id.is_(None)))
            .order_by(
                ModelPricing.provider,
                ModelPricing.model,
                ModelPricing.effective_from.desc(),
            )
        )
        return list(rows)

    async def find_effective(
        self,
        *,
        project_id: UUID,
        provider: str,
        model: str,
        at: datetime,
    ) -> ModelPricing | None:
        return await self.session.scalar(
            select(ModelPricing)
            .where(
                or_(ModelPricing.project_id == project_id, ModelPricing.project_id.is_(None)),
                ModelPricing.provider == provider,
                ModelPricing.model == model,
                ModelPricing.effective_from <= at,
                or_(ModelPricing.effective_to.is_(None), ModelPricing.effective_to > at),
            )
            .order_by(
                case((ModelPricing.project_id == project_id, 1), else_=0).desc(),
                ModelPricing.effective_from.desc(),
            )
            .limit(1)
        )

    async def list_custom_versions(
        self, project_id: UUID, provider: str, model: str
    ) -> list[ModelPricing]:
        rows = await self.session.scalars(
            select(ModelPricing)
            .where(
                ModelPricing.project_id == project_id,
                ModelPricing.provider == provider,
                ModelPricing.model == model,
            )
            .order_by(ModelPricing.effective_from)
            .with_for_update()
        )
        return list(rows)

    def add(self, pricing: ModelPricing) -> None:
        self.session.add(pricing)
