import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header

from agentscope_api.api.dependencies import (
    ProjectAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AuthenticationError, NotFoundError
from agentscope_api.models import FailureCluster, FailureRecord
from agentscope_api.repositories.failures import FailureRepository
from agentscope_api.schemas.failures import (
    FailureClusterResponse,
    FailureResponse,
    FailureSearchRequest,
    SimilarFailure,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.failure_intelligence import FailureIntelligenceService

router = APIRouter(tags=["Failure intelligence"])
internal_router = APIRouter(prefix="/internal/v1", tags=["Internal failure worker"])


def _require_worker_key(supplied: str | None, expected: str) -> None:
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise AuthenticationError("Invalid failure worker credential")


def _failure(record: FailureRecord) -> FailureResponse:
    return FailureResponse(
        id=record.id,
        project_id=record.project_id,
        trace_id=record.trace_id,
        failure_type=record.failure_type,
        title=record.title,
        document=record.document,
        evidence=record.evidence,
        agent_version=record.agent_version,
        detected_at=record.detected_at,
        created_at=record.created_at,
    )


async def _cluster(
    repository: FailureRepository, cluster: FailureCluster, *, include_members: bool = False
) -> FailureClusterResponse:
    return FailureClusterResponse(
        id=cluster.id,
        project_id=cluster.project_id,
        title=cluster.title,
        description=cluster.description,
        probable_cause=cluster.probable_cause,
        suggested_action=cluster.suggested_action,
        summary_source=cluster.summary_source,
        size=cluster.size,
        failure_percentage=cluster.failure_percentage,
        first_seen=cluster.first_seen,
        last_seen=cluster.last_seen,
        representative_failure_ids=[UUID(value) for value in cluster.representative_failure_ids],
        failure_ids=(await repository.cluster_failure_ids(cluster.id) if include_members else []),
    )


@router.post(
    "/projects/{project_id}/traces/{trace_id}/failure-analysis",
    response_model=FailureResponse | None,
)
async def analyze_failure(
    trace_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> FailureResponse | None:
    result = await FailureIntelligenceService(session, settings).analyze(
        access.project, access.membership, trace_id
    )
    return _failure(result) if result is not None else None


@router.get("/projects/{project_id}/failures", response_model=list[FailureResponse])
async def list_failures(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[FailureResponse]:
    require_permission(access.membership.role, Permission.TRACE_READ)
    return [
        _failure(record) for record in await FailureRepository(session).failures(access.project.id)
    ]


@router.get("/projects/{project_id}/failures/{failure_id}", response_model=FailureResponse)
async def get_failure(
    failure_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> FailureResponse:
    require_permission(access.membership.role, Permission.TRACE_READ)
    record = await FailureRepository(session).failure(failure_id, access.project.id)
    if record is None:
        raise NotFoundError("Failure")
    return _failure(record)


@router.post("/projects/{project_id}/failures/search", response_model=list[SimilarFailure])
async def search_failures(
    payload: FailureSearchRequest,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> list[SimilarFailure]:
    values = await FailureIntelligenceService(session, settings).search(
        access.project, access.membership, payload.query, payload.limit
    )
    return [SimilarFailure(failure=_failure(record), similarity=score) for record, score in values]


@router.post(
    "/projects/{project_id}/failure-clusters/rebuild",
    response_model=list[FailureClusterResponse],
)
async def rebuild_clusters(
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> list[FailureClusterResponse]:
    values = await FailureIntelligenceService(session, settings).rebuild_clusters(
        access.project, access.membership
    )
    repository = FailureRepository(session)
    return [await _cluster(repository, item) for item in values]


@router.get(
    "/projects/{project_id}/failure-clusters",
    response_model=list[FailureClusterResponse],
)
async def list_clusters(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[FailureClusterResponse]:
    require_permission(access.membership.role, Permission.TRACE_READ)
    repository = FailureRepository(session)
    return [
        await _cluster(repository, item) for item in await repository.clusters(access.project.id)
    ]


@router.get(
    "/projects/{project_id}/failure-clusters/{cluster_id}",
    response_model=FailureClusterResponse,
)
async def get_cluster(
    cluster_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> FailureClusterResponse:
    require_permission(access.membership.role, Permission.TRACE_READ)
    repository = FailureRepository(session)
    cluster = await repository.cluster(cluster_id, access.project.id)
    if cluster is None:
        raise NotFoundError("Failure cluster")
    return await _cluster(repository, cluster, include_members=True)


@internal_router.post(
    "/failures/analyze/{trace_id}",
    response_model=FailureResponse | None,
    include_in_schema=False,
)
async def analyze_failure_internal(
    trace_id: UUID,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> FailureResponse | None:
    _require_worker_key(worker_key, settings.worker_api_key)
    service = FailureIntelligenceService(session, settings)
    result = await service.analyze_internal(trace_id)
    if result is None:
        return None
    await service.rebuild_clusters_internal(result.project_id)
    return _failure(result)
