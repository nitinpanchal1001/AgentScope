from fastapi import APIRouter, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    ProjectAccessDependency,
    SessionDependency,
)
from agentscope_api.models import ModelPricing
from agentscope_api.repositories.pricing import PricingRepository
from agentscope_api.schemas.pricing import ModelPricingCreate, ModelPricingResponse
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.pricing import PricingService

router = APIRouter(tags=["Model pricing"])


def _response(pricing: ModelPricing) -> ModelPricingResponse:
    return ModelPricingResponse.model_validate(
        {
            "id": pricing.id,
            "project_id": pricing.project_id,
            "provider": pricing.provider,
            "model": pricing.model,
            "input_price_per_million_tokens": pricing.input_price_per_million_tokens,
            "output_price_per_million_tokens": pricing.output_price_per_million_tokens,
            "currency": pricing.currency,
            "source_url": pricing.source_url,
            "effective_from": pricing.effective_from,
            "effective_to": pricing.effective_to,
            "created_at": pricing.created_at,
            "custom": pricing.project_id is not None,
        }
    )


@router.get("/projects/{project_id}/model-pricing", response_model=list[ModelPricingResponse])
async def list_model_pricing(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[ModelPricingResponse]:
    require_permission(access.membership.role, Permission.PROJECT_READ)
    pricing = await PricingRepository(session).list_for_project(access.project.id)
    return [_response(item) for item in pricing]


@router.post(
    "/projects/{project_id}/model-pricing",
    response_model=ModelPricingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model_pricing(
    payload: ModelPricingCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> ModelPricingResponse:
    pricing = await PricingService(session).create_custom(
        access.project, access.membership, payload, user
    )
    return _response(pricing)
