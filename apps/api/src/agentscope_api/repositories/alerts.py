from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import AlertEvent, AlertRule


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rules(self, project_id: UUID) -> list[AlertRule]:
        values = await self.session.scalars(
            select(AlertRule)
            .where(AlertRule.project_id == project_id)
            .order_by(AlertRule.created_at.desc())
        )
        return list(values)

    async def rule(self, rule_id: UUID, project_id: UUID) -> AlertRule | None:
        return await self.session.scalar(
            select(AlertRule).where(AlertRule.id == rule_id, AlertRule.project_id == project_id)
        )

    async def enabled_rules(self) -> list[AlertRule]:
        values = await self.session.scalars(
            select(AlertRule).where(AlertRule.enabled.is_(True)).order_by(AlertRule.created_at)
        )
        return list(values)

    async def events(self, project_id: UUID, limit: int = 100) -> list[AlertEvent]:
        values = await self.session.scalars(
            select(AlertEvent)
            .where(AlertEvent.project_id == project_id)
            .order_by(AlertEvent.triggered_at.desc())
            .limit(limit)
        )
        return list(values)

    async def latest_event(self, rule_id: UUID) -> AlertEvent | None:
        return await self.session.scalar(
            select(AlertEvent)
            .where(AlertEvent.rule_id == rule_id)
            .order_by(AlertEvent.triggered_at.desc())
            .limit(1)
        )

    async def event(self, event_id: UUID) -> AlertEvent | None:
        return await self.session.get(AlertEvent, event_id)

    async def deduplication_exists(self, key: str) -> bool:
        return (
            await self.session.scalar(
                select(AlertEvent.id).where(AlertEvent.deduplication_key == key)
            )
        ) is not None
