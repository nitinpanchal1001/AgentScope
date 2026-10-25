from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.exceptions import ConflictError
from agentscope_api.models import Membership, ModelPricing, Project, User
from agentscope_api.repositories.pricing import PricingRepository
from agentscope_api.schemas.pricing import ModelPricingCreate
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission

MILLION = Decimal("1000000")
COST_QUANTUM = Decimal("0.000000000001")


def normalize_pricing_key(provider: str, model: str) -> tuple[str, str]:
    return provider.strip().lower(), model.strip().lower()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def calculate_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    input_price_per_million_tokens: Decimal,
    output_price_per_million_tokens: Decimal,
) -> Decimal:
    cost = (
        Decimal(input_tokens) * input_price_per_million_tokens
        + Decimal(output_tokens) * output_price_per_million_tokens
    ) / MILLION
    return cost.quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)


class PricingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PricingRepository(session)

    async def create_custom(
        self,
        project: Project,
        membership: Membership,
        request: ModelPricingCreate,
        user: User,
    ) -> ModelPricing:
        require_permission(membership.role, Permission.PRICING_MANAGE)
        provider, model = normalize_pricing_key(request.provider, request.model)
        effective_from = request.effective_from or datetime.now(UTC)
        if effective_from.tzinfo is None:
            effective_from = effective_from.replace(tzinfo=UTC)
        effective_to = request.effective_to
        if effective_to is not None and effective_to.tzinfo is None:
            effective_to = effective_to.replace(tzinfo=UTC)

        try:
            versions = await self.repository.list_custom_versions(project.id, provider, model)
            if any(_utc(item.effective_from) == effective_from for item in versions):
                raise ConflictError("A pricing version already starts at this time")
            previous = next(
                (item for item in reversed(versions) if _utc(item.effective_from) < effective_from),
                None,
            )
            following = next(
                (item for item in versions if _utc(item.effective_from) > effective_from),
                None,
            )
            if following is not None and (
                effective_to is None or effective_to > _utc(following.effective_from)
            ):
                effective_to = following.effective_from
            if previous is not None and (
                previous.effective_to is None or _utc(previous.effective_to) > effective_from
            ):
                previous.effective_to = effective_from
            pricing = ModelPricing(
                id=uuid4(),
                project_id=project.id,
                provider=provider,
                model=model,
                input_price_per_million_tokens=request.input_price_per_million_tokens,
                output_price_per_million_tokens=request.output_price_per_million_tokens,
                currency="USD",
                source_url=None,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=user.id,
                created_at=datetime.now(UTC),
            )
            self.repository.add(pricing)
            record_audit(
                self.session,
                organization_id=project.organization_id,
                actor_id=user.id,
                action="model_pricing.created",
                resource_type="model_pricing",
                resource_id=pricing.id,
                metadata={"provider": provider, "model": model},
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return pricing
