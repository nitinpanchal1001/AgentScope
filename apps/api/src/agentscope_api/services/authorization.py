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
    PRICING_MANAGE = "pricing:manage"
    DATA_WRITE = "data:write"
    TRACE_READ = "trace:read"
    ANALYTICS_READ = "analytics:read"
    EVALUATOR_MANAGE = "evaluator:manage"
    EVALUATION_RUN = "evaluation:run"
    DATASET_READ = "dataset:read"
    DATASET_MANAGE = "dataset:manage"
    EXPERIMENT_READ = "experiment:read"
    EXPERIMENT_MANAGE = "experiment:manage"
    EXPERIMENT_RUN = "experiment:run"
    QUALITY_GATE_READ = "quality_gate:read"
    QUALITY_GATE_MANAGE = "quality_gate:manage"
    REPLAY_READ = "replay:read"
    REPLAY_RUN = "replay:run"
    ALERT_READ = "alert:read"
    ALERT_MANAGE = "alert:manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PROJECT_READ,
            Permission.PROJECT_MANAGE,
            Permission.API_KEY_MANAGE,
            Permission.PRICING_MANAGE,
            Permission.DATA_WRITE,
            Permission.TRACE_READ,
            Permission.ANALYTICS_READ,
            Permission.EVALUATOR_MANAGE,
            Permission.EVALUATION_RUN,
            Permission.DATASET_READ,
            Permission.DATASET_MANAGE,
            Permission.EXPERIMENT_READ,
            Permission.EXPERIMENT_MANAGE,
            Permission.EXPERIMENT_RUN,
            Permission.QUALITY_GATE_READ,
            Permission.QUALITY_GATE_MANAGE,
            Permission.REPLAY_READ,
            Permission.REPLAY_RUN,
            Permission.ALERT_READ,
            Permission.ALERT_MANAGE,
        }
    ),
    Role.MEMBER: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PROJECT_READ,
            Permission.DATA_WRITE,
            Permission.TRACE_READ,
            Permission.ANALYTICS_READ,
            Permission.EVALUATION_RUN,
            Permission.DATASET_READ,
            Permission.DATASET_MANAGE,
            Permission.EXPERIMENT_READ,
            Permission.EXPERIMENT_MANAGE,
            Permission.EXPERIMENT_RUN,
            Permission.QUALITY_GATE_READ,
            Permission.QUALITY_GATE_MANAGE,
            Permission.REPLAY_READ,
            Permission.REPLAY_RUN,
            Permission.ALERT_READ,
            Permission.ALERT_MANAGE,
        }
    ),
    Role.VIEWER: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PROJECT_READ,
            Permission.TRACE_READ,
            Permission.ANALYTICS_READ,
            Permission.DATASET_READ,
            Permission.EXPERIMENT_READ,
            Permission.QUALITY_GATE_READ,
            Permission.REPLAY_READ,
            Permission.ALERT_READ,
        }
    ),
}


def require_permission(role: Role, permission: Permission) -> None:
    if permission not in ROLE_PERMISSIONS[role]:
        raise PermissionDeniedError()
