from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.config import Settings, get_settings
from agentscope_api.core.database import get_session
from agentscope_api.core.exceptions import AuthenticationError, NotFoundError
from agentscope_api.core.security import decode_access_token, keyed_hash
from agentscope_api.models import ApiKey, Membership, Organization, Project, User
from agentscope_api.repositories.auth import AuthRepository
from agentscope_api.repositories.organizations import OrganizationRepository
from agentscope_api.repositories.projects import ProjectRepository

SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDependency,
    settings: SettingsDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except (jwt.InvalidTokenError, ValueError) as error:
        raise AuthenticationError("Invalid or expired access token") from error
    user = await AuthRepository(session).get_user(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True)
class OrganizationAccess:
    organization: Organization
    membership: Membership


async def get_organization_access(
    organization_id: UUID, session: SessionDependency, user: CurrentUser
) -> OrganizationAccess:
    result = await OrganizationRepository(session).get(organization_id, user.id)
    if result is None:
        # Do not reveal whether another tenant owns this UUID.
        raise NotFoundError("Organization")
    organization, membership = result
    return OrganizationAccess(organization, membership)


OrganizationAccessDependency = Annotated[OrganizationAccess, Depends(get_organization_access)]


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    membership: Membership


async def get_project_access(
    project_id: UUID, session: SessionDependency, user: CurrentUser
) -> ProjectAccess:
    result = await ProjectRepository(session).get_scoped(project_id, user.id)
    if result is None:
        raise NotFoundError("Project")
    project, membership = result
    return ProjectAccess(project, membership)


ProjectAccessDependency = Annotated[ProjectAccess, Depends(get_project_access)]


@dataclass(frozen=True)
class IngestionAccess:
    api_key: ApiKey
    project: Project


async def get_ingestion_access(
    session: SessionDependency,
    settings: SettingsDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> IngestionAccess:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("A project API key is required")
    raw_key = credentials.credentials
    if not raw_key.startswith(("as_live_", "as_test_")):
        raise AuthenticationError("Invalid project API key")
    result = await ProjectRepository(session).get_active_api_key_by_hash(
        keyed_hash(raw_key, settings.token_hash_secret)
    )
    if result is None:
        raise AuthenticationError("Invalid or revoked project API key")
    api_key, project = result
    api_key.last_used_at = datetime.now(UTC)
    return IngestionAccess(api_key=api_key, project=project)


IngestionAccessDependency = Annotated[IngestionAccess, Depends(get_ingestion_access)]
