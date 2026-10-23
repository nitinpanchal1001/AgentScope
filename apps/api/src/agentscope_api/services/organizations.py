from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.database_errors import is_unique_violation
from agentscope_api.core.exceptions import ConflictError
from agentscope_api.core.slugs import append_slug_suffix, slugify
from agentscope_api.models import Membership, Organization, Role, User
from agentscope_api.repositories.organizations import OrganizationRepository
from agentscope_api.schemas.organizations import OrganizationCreate
from agentscope_api.services.audit import record_audit


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = OrganizationRepository(session)

    async def create(self, request: OrganizationCreate, user: User) -> Organization:
        try:
            organization_id = uuid4()
            slug = slugify(request.name, fallback="organization")
            if await self.repository.slug_exists(slug):
                slug = append_slug_suffix(slug, organization_id.hex[:8])
            organization = Organization(
                id=organization_id, name=request.name.strip(), slug=slug, settings={}
            )
            membership = Membership(
                id=uuid4(), organization_id=organization.id, user_id=user.id, role=Role.OWNER
            )
            self.repository.add(organization, membership)
            # The audit record references this new organization. Flush the
            # tenant root first so PostgreSQL cannot schedule the audit insert
            # ahead of its foreign-key target.
            await self.session.flush()
            record_audit(
                self.session,
                organization_id=organization.id,
                actor_id=user.id,
                action="organization.created",
                resource_type="organization",
                resource_id=organization.id,
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            if not is_unique_violation(error):
                raise
            raise ConflictError("Organization could not be created; please retry") from error
        return organization
