import enum

from agentscope_api.core.exceptions import PermissionDeniedError
from agentscope_api.models import Role


class Permission(enum.StrEnum):
    ORGANIZATION_READ = "organization:read"
    ORGANIZATION_MANAGE = "organization:manage"
    MEMBERS_MANAGE = "members:manage"
    PROJECT_READ = "project:read"
    PROJECT_MANAGE = "project:manage"
    API_KEY_MANAGE = "api_key:manage"
    DATA_WRITE = "data:write"
    TRACE_READ = "trace:read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PROJECT_READ,
            Permission.PROJECT_MANAGE,
            Permission.API_KEY_MANAGE,
            Permission.DATA_WRITE,
            Permission.TRACE_READ,
        }
    ),
    Role.MEMBER: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PROJECT_READ,
            Permission.DATA_WRITE,
            Permission.TRACE_READ,
        }
    ),
    Role.VIEWER: frozenset(
        {Permission.ORGANIZATION_READ, Permission.PROJECT_READ, Permission.TRACE_READ}
    ),
}


def require_permission(role: Role, permission: Permission) -> None:
    if permission not in ROLE_PERMISSIONS[role]:
        raise PermissionDeniedError()
