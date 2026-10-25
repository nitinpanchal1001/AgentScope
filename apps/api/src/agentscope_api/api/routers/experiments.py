import math
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    ProjectAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AuthenticationError, NotFoundError
from agentscope_api.models import Dataset, DatasetItem, DatasetVersion, Experiment, ExperimentRun
from agentscope_api.repositories.experiments import ExperimentRepository
from agentscope_api.schemas.experiments import (
    ExperimentCreate,
    ExperimentResponse,
    ExperimentRunPage,
    ExperimentRunResponse,
    HttpAgentConfiguration,
    WorkerExperimentRunCompletion,
    WorkerExperimentRunCompletionResponse,
    WorkerExperimentRunPayload,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.experiment_dispatch import dispatch_experiment_run
from agentscope_api.services.experiments import ExperimentService

router = APIRouter(tags=["Experiments"])
internal_router = APIRouter(prefix="/internal/v1", tags=["Internal experiment worker"])


def _experiment_response(
    experiment: Experiment,
    version: DatasetVersion,
    dataset: Dataset,
    evaluator_version_ids: list[UUID],
) -> ExperimentResponse:
    return ExperimentResponse(
        id=experiment.id,
        organization_id=experiment.organization_id,
        project_id=experiment.project_id,
        environment_id=experiment.environment_id,
        dataset_version_id=experiment.dataset_version_id,
        dataset_name=dataset.name,
        dataset_version=version.version,
        name=experiment.name,
        description=experiment.description,
        status=experiment.status,
        agent=HttpAgentConfiguration.model_validate(experiment.agent_configuration),
        evaluator_version_ids=evaluator_version_ids,
        max_concurrency=experiment.max_concurrency,
        total_cases=experiment.total_cases,
        completed_cases=experiment.completed_cases,
        passed_cases=experiment.passed_cases,
        failed_cases=experiment.failed_cases,
        metrics=experiment.metrics,
        cancel_requested=experiment.cancel_requested,
        error_message=experiment.error_message,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        started_at=experiment.started_at,
        completed_at=experiment.completed_at,
    )


def _run_response(run: ExperimentRun, item: DatasetItem) -> ExperimentRunResponse:
    return ExperimentRunResponse(
        id=run.id,
        experiment_id=run.experiment_id,
        dataset_item_id=run.dataset_item_id,
        trace_id=run.trace_id,
        ordinal=run.ordinal,
        status=run.status,
        input=item.input,
        expected_output=item.expected_output,
        expected_tools=item.expected_tools,
        output=run.output,
        latency_ms=run.latency_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens,
        total_cost=run.total_cost,
        evaluation_score=run.evaluation_score,
        passed=run.passed,
        error_type=run.error_type,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


async def _detail(
    repository: ExperimentRepository, experiment_id: UUID, project_id: UUID
) -> tuple[Experiment, DatasetVersion, Dataset, list[UUID]]:
    value = await repository.get_experiment(experiment_id, project_id)
    if value is None:
        raise NotFoundError("Experiment")
    return value


@router.get("/projects/{project_id}/experiments", response_model=list[ExperimentResponse])
async def list_experiments(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[ExperimentResponse]:
    require_permission(access.membership.role, Permission.EXPERIMENT_READ)
    rows = await ExperimentRepository(session).list_experiments(access.project.id)
    return [_experiment_response(*row) for row in rows]


@router.post(
    "/projects/{project_id}/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(
    payload: ExperimentCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> ExperimentResponse:
    experiment = await ExperimentService(session).create(
        access.project, access.membership, payload, user
    )
    return _experiment_response(
        *await _detail(ExperimentRepository(session), experiment.id, access.project.id)
    )


@router.get(
    "/projects/{project_id}/experiments/{experiment_id}",
    response_model=ExperimentResponse,
)
async def get_experiment(
    experiment_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> ExperimentResponse:
    require_permission(access.membership.role, Permission.EXPERIMENT_READ)
    return _experiment_response(
        *await _detail(ExperimentRepository(session), experiment_id, access.project.id)
    )


@router.get(
    "/projects/{project_id}/experiments/{experiment_id}/runs",
    response_model=ExperimentRunPage,
)
async def list_experiment_runs(
    experiment_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ExperimentRunPage:
    require_permission(access.membership.role, Permission.EXPERIMENT_READ)
    experiment, _, _, _ = await _detail(
        ExperimentRepository(session), experiment_id, access.project.id
    )
    total_pages = max(1, math.ceil(experiment.total_cases / page_size))
    rows = await ExperimentRepository(session).list_runs(
        experiment.id, offset=(page - 1) * page_size, limit=page_size
    )
    return ExperimentRunPage(
        items=[_run_response(*row) for row in rows],
        page=page,
        page_size=page_size,
        total_items=experiment.total_cases,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


@router.post(
    "/projects/{project_id}/experiments/{experiment_id}/start",
    response_model=ExperimentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_experiment(
    experiment_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> ExperimentResponse:
    run_ids = await ExperimentService(session).start(
        access.project, access.membership, experiment_id, user
    )
    failed_dispatches: list[UUID] = []
    for run_id in run_ids:
        if not dispatch_experiment_run(run_id):
            failed_dispatches.append(run_id)
    await ExperimentService(session).handle_initial_dispatch_failures(
        experiment_id,
        failed_dispatches,
        all_failed=bool(run_ids) and len(failed_dispatches) == len(run_ids),
    )
    return _experiment_response(
        *await _detail(ExperimentRepository(session), experiment_id, access.project.id)
    )


@router.post(
    "/projects/{project_id}/experiments/{experiment_id}/cancel",
    response_model=ExperimentResponse,
)
async def cancel_experiment(
    experiment_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> ExperimentResponse:
    await ExperimentService(session).cancel(access.project, access.membership, experiment_id, user)
    return _experiment_response(
        *await _detail(ExperimentRepository(session), experiment_id, access.project.id)
    )


def _require_worker_key(supplied: str | None, expected: str) -> None:
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise AuthenticationError("Invalid experiment worker credential")


@internal_router.get(
    "/experiment-runs/{run_id}/payload",
    response_model=WorkerExperimentRunPayload,
    include_in_schema=False,
)
async def get_experiment_run_payload(
    run_id: UUID,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> WorkerExperimentRunPayload:
    _require_worker_key(worker_key, settings.worker_api_key)
    return await ExperimentService(session).worker_payload(run_id)


@internal_router.post(
    "/experiment-runs/{run_id}/complete",
    response_model=WorkerExperimentRunCompletionResponse,
    include_in_schema=False,
)
async def complete_experiment_run(
    run_id: UUID,
    payload: WorkerExperimentRunCompletion,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> WorkerExperimentRunCompletionResponse:
    _require_worker_key(worker_key, settings.worker_api_key)
    return await ExperimentService(session).complete_invocation(run_id, payload)
