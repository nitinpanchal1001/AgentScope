import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    ProjectAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AuthenticationError, NotFoundError
from agentscope_api.models import TraceReplay
from agentscope_api.repositories.replays import ReplayRepository
from agentscope_api.schemas.experiments import HttpAgentConfiguration
from agentscope_api.schemas.replays import (
    ReplayComparison,
    ReplayCreate,
    ReplayOverrides,
    ReplayResponse,
    WorkerReplayCompletion,
    WorkerReplayCompletionResponse,
    WorkerReplayPayload,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.replay_dispatch import dispatch_replay
from agentscope_api.services.replays import ReplayService

router = APIRouter(tags=["Replays"])
internal_router = APIRouter(prefix="/internal/v1", tags=["Internal replay worker"])


def _response(replay: TraceReplay) -> ReplayResponse:
    return ReplayResponse(
        id=replay.id,
        organization_id=replay.organization_id,
        project_id=replay.project_id,
        environment_id=replay.environment_id,
        original_trace_id=replay.original_trace_id,
        replay_trace_id=replay.replay_trace_id,
        status=replay.status,
        agent=HttpAgentConfiguration.model_validate(replay.agent_configuration),
        overrides=ReplayOverrides.model_validate(replay.overrides),
        effective_configuration=replay.effective_configuration,
        error_type=replay.error_type,
        error_message=replay.error_message,
        created_at=replay.created_at,
        updated_at=replay.updated_at,
        started_at=replay.started_at,
        completed_at=replay.completed_at,
    )


@router.post(
    "/projects/{project_id}/traces/{trace_id}/replays",
    response_model=ReplayResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_replay(
    trace_id: UUID,
    payload: ReplayCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> ReplayResponse:
    service = ReplayService(session)
    replay = await service.create(access.project, access.membership, trace_id, payload, user)
    if not dispatch_replay(replay.id):
        await service.dispatch_failed(replay.id)
    return _response(replay)


@router.get(
    "/projects/{project_id}/traces/{trace_id}/replays",
    response_model=list[ReplayResponse],
)
async def list_replays(
    trace_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> list[ReplayResponse]:
    require_permission(access.membership.role, Permission.REPLAY_READ)
    repository = ReplayRepository(session)
    if await repository.trace(trace_id, access.project.id) is None:
        raise NotFoundError("Trace")
    return [
        _response(replay)
        for replay in await repository.list_for_original(trace_id, access.project.id)
    ]


@router.get("/projects/{project_id}/replays/{replay_id}", response_model=ReplayResponse)
async def get_replay(
    replay_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> ReplayResponse:
    require_permission(access.membership.role, Permission.REPLAY_READ)
    replay = await ReplayRepository(session).replay(replay_id, access.project.id)
    if replay is None:
        raise NotFoundError("Replay")
    return _response(replay)


@router.get(
    "/projects/{project_id}/replays/{replay_id}/comparison",
    response_model=ReplayComparison,
)
async def compare_replay(
    replay_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> ReplayComparison:
    return await ReplayService(session).comparison(access.project, access.membership, replay_id)


def _require_worker_key(supplied: str | None, expected: str) -> None:
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise AuthenticationError("Invalid replay worker credential")


@internal_router.get(
    "/replays/{replay_id}/payload",
    response_model=WorkerReplayPayload,
    include_in_schema=False,
)
async def replay_payload(
    replay_id: UUID,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> WorkerReplayPayload:
    _require_worker_key(worker_key, settings.worker_api_key)
    return await ReplayService(session).worker_payload(replay_id)


@internal_router.post(
    "/replays/{replay_id}/complete",
    response_model=WorkerReplayCompletionResponse,
    include_in_schema=False,
)
async def complete_replay(
    replay_id: UUID,
    payload: WorkerReplayCompletion,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> WorkerReplayCompletionResponse:
    _require_worker_key(worker_key, settings.worker_api_key)
    return await ReplayService(session).complete(replay_id, payload)
