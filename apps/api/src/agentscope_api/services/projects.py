from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.config import Settings
from agentscope_api.core.database_errors import is_unique_violation
from agentscope_api.core.exceptions import ConflictError, NotFoundError
from agentscope_api.core.security import generate_api_key, keyed_hash
from agentscope_api.core.slugs import append_slug_suffix, slugify
from agentscope_api.models import ApiKey, Environment, Membership, Project, User
from agentscope_api.repositories.projects import ProjectRepository
from agentscope_api.schemas.projects import ApiKeyCreate, ProjectCreate, ProjectRetentionUpdate
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission

DEFAULT_ENVIRONMENTS = (
    ("Development", "development"),
    ("Staging", "staging"),
    ("Production", "production"),
)


class ProjectService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = ProjectRepository(session)

    async def create(
        self, organization_id: UUID, request: ProjectCreate, user: User, membership: Membership
    ) -> Project:
        require_permission(membership.role, Permission.PROJECT_MANAGE)
        try:
            project_id = uuid4()
            slug = slugify(request.name, fallback="project")
            if await self.repository.slug_exists(organization_id, slug):
                slug = append_slug_suffix(slug, project_id.hex[:8])
            project = Project(
                id=project_id,
                organization_id=organization_id,
                name=request.name.strip(),
                slug=slug,
                description=request.description,
                retention_days=request.retention_days,
            )
            environments = [
                Environment(id=uuid4(), project_id=project.id, name=name, slug=slug)
                for name, slug in DEFAULT_ENVIRONMENTS
            ]
            self.repository.add_project(project)
            await self.session.flush()
            self.repository.add_environments(environments)
            record_audit(
                self.session,
                organization_id=organization_id,
                actor_id=user.id,
                action="project.created",
                resource_type="project",
                resource_id=project.id,
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            if not is_unique_violation(error):
                raise
            raise ConflictError("Project could not be created; please retry") from error
        return project

    async def issue_api_key(
        self, project: Project, membership: Membership, request: ApiKeyCreate, user: User
    ) -> tuple[ApiKey, str]:
        require_permission(membership.role, Permission.API_KEY_MANAGE)
        try:
            environment = await self.repository.get_environment(project.id, request.environment_id)
            if environment is None:
                raise NotFoundError("Environment")
            raw_key, prefix = generate_api_key(environment.slug)
            api_key = ApiKey(
                id=uuid4(),
                project_id=project.id,
                environment_id=environment.id,
                name=request.name.strip(),
                prefix=prefix,
                key_hash=keyed_hash(raw_key, self.settings.token_hash_secret),
                created_at=datetime.now(UTC),
                last_used_at=None,
                revoked_at=None,
                created_by=user.id,
            )
            self.repository.add_api_key(api_key)
            record_audit(
                self.session,
                organization_id=project.organization_id,
                actor_id=user.id,
                action="api_key.created",
                resource_type="api_key",
                resource_id=api_key.id,
                metadata={"prefix": prefix, "environment_id": str(environment.id)},
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return api_key, raw_key

    async def update_retention(
        self,
        project: Project,
        membership: Membership,
        request: ProjectRetentionUpdate,
        user: User,
    ) -> Project:
        require_permission(membership.role, Permission.PROJECT_MANAGE)
        project.retention_days = request.retention_days
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="project.retention_updated",
            resource_type="project",
            resource_id=project.id,
            metadata={"retention_days": request.retention_days},
        )
        await self.session.commit()
        return project

    async def revoke_api_key(
        self, project: Project, membership: Membership, api_key_id: UUID, user: User
    ) -> ApiKey:
        require_permission(membership.role, Permission.API_KEY_MANAGE)
        try:
            api_key = await self.repository.get_api_key(project.id, api_key_id)
            if api_key is None:
                raise NotFoundError("API key")
            if api_key.revoked_at is None:
                api_key.revoked_at = datetime.now(UTC)
                record_audit(
                    self.session,
                    organization_id=project.organization_id,
                    actor_id=user.id,
                    action="api_key.revoked",
                    resource_type="api_key",
                    resource_id=api_key.id,
                    metadata={"prefix": api_key.prefix},
                )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return api_key
