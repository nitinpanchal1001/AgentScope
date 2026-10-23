from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import AuditLog
from agentscope_api.models.base import utc_now


def record_audit(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            audit_metadata=metadata or {},
            created_at=utc_now(),
        )
    )
