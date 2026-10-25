import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, Response, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    ProjectAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AuthenticationError
from agentscope_api.models import EvaluationResult, Evaluator, EvaluatorVersion
from agentscope_api.repositories.evaluations import EvaluationRepository
from agentscope_api.schemas.evaluations import (
    EvaluationBindingCreate,
    EvaluationBindingResponse,
    EvaluationBindingUpdate,
    EvaluationResultResponse,
    EvaluationRunRequest,
    EvaluatorCreate,
    EvaluatorResponse,
    EvaluatorStateUpdate,
    EvaluatorVersionCreate,
    EvaluatorVersionResponse,
    WorkerEvaluationCompletion,
    WorkerEvaluationPayload,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.evaluation_dispatch import dispatch_evaluation
from agentscope_api.services.evaluations import EvaluationService
from agentscope_api.services.failure_dispatch import dispatch_failure_analysis

router = APIRouter(tags=["Evaluations"])
internal_router = APIRouter(prefix="/internal/v1", tags=["Internal evaluation worker"])


def _evaluator_response(
    evaluator: Evaluator, versions: list[EvaluatorVersion]
) -> EvaluatorResponse:
    return EvaluatorResponse(
        id=evaluator.id,
        organization_id=evaluator.organization_id,
        project_id=evaluator.project_id,
        name=evaluator.name,
        description=evaluator.description,
        enabled=evaluator.enabled,
        created_at=evaluator.created_at,
        updated_at=evaluator.updated_at,
        versions=[EvaluatorVersionResponse.model_validate(item) for item in versions],
    )


def _result_response(
    result: EvaluationResult, version: EvaluatorVersion, evaluator: Evaluator
) -> EvaluationResultResponse:
    return EvaluationResultResponse(
        id=result.id,
        trace_id=result.trace_id,
        evaluator_id=evaluator.id,
        evaluator_name=evaluator.name,
        evaluator_version_id=version.id,
        evaluator_version=version.version,
        evaluator_type=version.type,
        source=result.source,
        status=result.status,
        threshold=result.threshold,
        score=result.score,
        passed=result.passed,
        label=result.label,
        reason=result.reason,
        evidence=result.evidence,
        metadata=result.result_metadata,
        error_type=result.error_type,
        error_message=result.error_message,
        created_at=result.created_at,
        started_at=result.started_at,
        completed_at=result.completed_at,
    )


@router.get("/projects/{project_id}/evaluators", response_model=list[EvaluatorResponse])
async def list_evaluators(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[EvaluatorResponse]:
    require_permission(access.membership.role, Permission.PROJECT_READ)
    rows = await EvaluationRepository(session).list_evaluators(access.project.id)
    return [_evaluator_response(evaluator, versions) for evaluator, versions in rows]


@router.post(
    "/projects/{project_id}/evaluators",
    response_model=EvaluatorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluator(
    payload: EvaluatorCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> EvaluatorResponse:
    evaluator, versions = await EvaluationService(session).create_evaluator(
        access.project, access.membership, payload, user
    )
    return _evaluator_response(evaluator, versions)


@router.post(
    "/projects/{project_id}/evaluators/{evaluator_id}/versions",
    response_model=EvaluatorVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluator_version(
    evaluator_id: UUID,
    payload: EvaluatorVersionCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> EvaluatorVersionResponse:
    version = await EvaluationService(session).create_version(
        access.project, access.membership, evaluator_id, payload, user
    )
    return EvaluatorVersionResponse.model_validate(version)


@router.patch(
    "/projects/{project_id}/evaluators/{evaluator_id}",
    response_model=EvaluatorResponse,
)
async def update_evaluator_state(
    evaluator_id: UUID,
    payload: EvaluatorStateUpdate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> EvaluatorResponse:
    evaluator = await EvaluationService(session).set_evaluator_enabled(
        access.project, access.membership, evaluator_id, payload.enabled, user
    )
    rows = await EvaluationRepository(session).list_evaluators(access.project.id)
    versions = next(versions for item, versions in rows if item.id == evaluator.id)
    return _evaluator_response(evaluator, versions)


@router.get(
    "/projects/{project_id}/evaluation-bindings",
    response_model=list[EvaluationBindingResponse],
)
async def list_evaluation_bindings(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[EvaluationBindingResponse]:
    require_permission(access.membership.role, Permission.PROJECT_READ)
    bindings = await EvaluationRepository(session).list_bindings(access.project.id)
    return [EvaluationBindingResponse.model_validate(item) for item in bindings]


@router.post(
    "/projects/{project_id}/evaluation-bindings",
    response_model=EvaluationBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluation_binding(
    payload: EvaluationBindingCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> EvaluationBindingResponse:
    binding = await EvaluationService(session).create_binding(
        access.project, access.membership, payload, user
    )
    return EvaluationBindingResponse.model_validate(binding)


@router.patch(
    "/projects/{project_id}/evaluation-bindings/{binding_id}",
    response_model=EvaluationBindingResponse,
)
async def update_evaluation_binding(
    binding_id: UUID,
    payload: EvaluationBindingUpdate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> EvaluationBindingResponse:
    binding = await EvaluationService(session).update_binding(
        access.project, access.membership, binding_id, payload, user
    )
    return EvaluationBindingResponse.model_validate(binding)


@router.get(
    "/projects/{project_id}/traces/{trace_id}/evaluations",
    response_model=list[EvaluationResultResponse],
)
async def list_trace_evaluations(
    trace_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> list[EvaluationResultResponse]:
    require_permission(access.membership.role, Permission.TRACE_READ)
    rows = await EvaluationRepository(session).list_results_for_trace(trace_id, access.project.id)
    return [_result_response(*row) for row in rows]


@router.post(
    "/projects/{project_id}/traces/{trace_id}/evaluations",
    response_model=list[EvaluationResultResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_trace_evaluations(
    trace_id: UUID,
    payload: EvaluationRunRequest,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> list[EvaluationResultResponse]:
    service = EvaluationService(session)
    results = await service.prepare_manual(
        access.project,
        access.membership,
        trace_id,
        payload.evaluator_version_ids,
    )
    for result in results:
        dispatch_evaluation(result.id)
    rows = await EvaluationRepository(session).list_results_for_trace(trace_id, access.project.id)
    selected = {result.id for result in results}
    return [_result_response(*row) for row in rows if row[0].id in selected]


def _require_worker_key(supplied: str | None, expected: str) -> None:
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise AuthenticationError("Invalid evaluation worker credential")


@internal_router.get(
    "/evaluation-results/{result_id}/payload",
    response_model=WorkerEvaluationPayload,
    include_in_schema=False,
)
async def get_worker_payload(
    result_id: UUID,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> WorkerEvaluationPayload:
    _require_worker_key(worker_key, settings.worker_api_key)
    return await EvaluationService(session).worker_payload(result_id)


@internal_router.post(
    "/evaluation-results/{result_id}/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def complete_worker_evaluation(
    result_id: UUID,
    payload: WorkerEvaluationCompletion,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> Response:
    _require_worker_key(worker_key, settings.worker_api_key)
    result = await EvaluationService(session).complete(result_id, payload)
    background_tasks.add_task(dispatch_failure_analysis, result.trace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
