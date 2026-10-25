from uuid import UUID

from fastapi import APIRouter, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    OrganizationAccessDependency,
    ProjectAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.repositories.projects import ProjectRepository
from agentscope_api.schemas.projects import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    EnvironmentResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectRetentionUpdate,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.projects import ProjectService

router = APIRouter(tags=["Projects"])


@router.post(
    "/organizations/{organization_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    organization_id: UUID,
    payload: ProjectCreate,
    access: OrganizationAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
) -> ProjectResponse:
    project = await ProjectService(session, settings).create(
        organization_id, payload, user, access.membership
    )
    return ProjectResponse.model_validate(project)


@router.get("/organizations/{organization_id}/projects", response_model=list[ProjectResponse])
async def list_projects(
    organization_id: UUID,
    access: OrganizationAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> list[ProjectResponse]:
    require_permission(access.membership.role, Permission.PROJECT_READ)
    projects = await ProjectRepository(session).list_for_organization(organization_id, user.id)
    return [ProjectResponse.model_validate(project) for project in projects]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, access: ProjectAccessDependency) -> ProjectResponse:
    return ProjectResponse.model_validate(access.project)


@router.patch("/projects/{project_id}/retention", response_model=ProjectResponse)
async def update_project_retention(
    payload: ProjectRetentionUpdate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
) -> ProjectResponse:
    project = await ProjectService(session, settings).update_retention(
        access.project, access.membership, payload, user
    )
    return ProjectResponse.model_validate(project)


@router.get("/projects/{project_id}/environments", response_model=list[EnvironmentResponse])
async def list_environments(
    project_id: UUID, access: ProjectAccessDependency, session: SessionDependency
) -> list[EnvironmentResponse]:
    require_permission(access.membership.role, Permission.PROJECT_READ)
    environments = await ProjectRepository(session).list_environments(project_id)
    return [EnvironmentResponse.model_validate(item) for item in environments]


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    project_id: UUID,
    payload: ApiKeyCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
) -> ApiKeyCreated:
    api_key, raw_key = await ProjectService(session, settings).issue_api_key(
        access.project, access.membership, payload, user
    )
    base = ApiKeyResponse.model_validate(api_key)
    return ApiKeyCreated(**base.model_dump(), key=raw_key)


@router.get("/projects/{project_id}/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    project_id: UUID, access: ProjectAccessDependency, session: SessionDependency
) -> list[ApiKeyResponse]:
    require_permission(access.membership.role, Permission.API_KEY_MANAGE)
    keys = await ProjectRepository(session).list_api_keys(project_id)
    return [ApiKeyResponse.model_validate(key) for key in keys]


@router.delete("/projects/{project_id}/api-keys/{api_key_id}", response_model=ApiKeyResponse)
async def revoke_api_key(
    project_id: UUID,
    api_key_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
) -> ApiKeyResponse:
    api_key = await ProjectService(session, settings).revoke_api_key(
        access.project, access.membership, api_key_id, user
    )
    return ApiKeyResponse.model_validate(api_key)
