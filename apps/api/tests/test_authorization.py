import pytest

from agentscope_api.core.exceptions import PermissionDeniedError
from agentscope_api.models import Role
from agentscope_api.services.authorization import Permission, require_permission


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN])
def test_api_key_permission_allowed(role: Role) -> None:
    require_permission(role, Permission.API_KEY_MANAGE)


@pytest.mark.parametrize("role", [Role.MEMBER, Role.VIEWER])
def test_api_key_permission_denied(role: Role) -> None:
    with pytest.raises(PermissionDeniedError):
        require_permission(role, Permission.API_KEY_MANAGE)
