import secrets
from typing import Annotated

from fastapi import APIRouter, Header

from agentscope_api.api.dependencies import SessionDependency, SettingsDependency
from agentscope_api.core.exceptions import AuthenticationError
from agentscope_api.schemas.maintenance import RetentionRunResponse
from agentscope_api.services.maintenance import MaintenanceService

internal_router = APIRouter(prefix="/internal/v1", tags=["Internal maintenance worker"])


@internal_router.post(
    "/maintenance/retention",
    response_model=RetentionRunResponse,
    include_in_schema=False,
)
async def expire_telemetry(
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> RetentionRunResponse:
    if worker_key is None or not secrets.compare_digest(worker_key, settings.worker_api_key):
        raise AuthenticationError("Invalid maintenance worker credential")
    return await MaintenanceService(session, settings).expire_telemetry()
