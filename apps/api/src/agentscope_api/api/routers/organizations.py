from uuid import UUID

from fastapi import APIRouter, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    OrganizationAccessDependency,
    SessionDependency,
)
from agentscope_api.models import Role
from agentscope_api.repositories.organizations import OrganizationRepository
from agentscope_api.schemas.organizations import (
    MemberResponse,
    OrganizationCreate,
    OrganizationResponse,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.organizations import OrganizationService

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate, session: SessionDependency, user: CurrentUser
) -> OrganizationResponse:
    organization = await OrganizationService(session).create(payload, user)
    return OrganizationResponse.model_validate(organization).model_copy(update={"role": Role.OWNER})


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    session: SessionDependency, user: CurrentUser
) -> list[OrganizationResponse]:
    rows = await OrganizationRepository(session).list_for_user(user.id)
    return [
        OrganizationResponse.model_validate(org).model_copy(update={"role": membership.role})
        for org, membership in rows
    ]


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: UUID, access: OrganizationAccessDependency
) -> OrganizationResponse:
    return OrganizationResponse.model_validate(access.organization).model_copy(
        update={"role": access.membership.role}
    )


@router.get("/{organization_id}/members", response_model=list[MemberResponse])
async def list_members(
    organization_id: UUID,
    access: OrganizationAccessDependency,
    session: SessionDependency,
) -> list[MemberResponse]:
    require_permission(access.membership.role, Permission.ORGANIZATION_READ)
    rows = await OrganizationRepository(session).list_members(organization_id)
    return [
        MemberResponse(
            id=membership.id,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]
