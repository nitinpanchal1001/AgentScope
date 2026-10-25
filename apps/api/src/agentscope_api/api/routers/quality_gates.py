from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from agentscope_api.api.dependencies import CurrentUser, ProjectAccessDependency, SessionDependency
from agentscope_api.core.exceptions import ConflictError, NotFoundError
from agentscope_api.models import ExperimentBaseline, QualityGate, QualityGateResult
from agentscope_api.repositories.quality_gates import QualityGateRepository
from agentscope_api.schemas.quality_gates import (
    BaselineResponse,
    MetricComparison,
    QualityGateCreate,
    QualityGateResponse,
    QualityGateResultResponse,
    QualityGateRule,
    QualityGateRunRequest,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.quality_gates import QualityGateService, compare_metrics

router = APIRouter(tags=["Quality gates"])


def _gate_response(gate: QualityGate) -> QualityGateResponse:
    return QualityGateResponse(
        id=gate.id,
        project_id=gate.project_id,
        name=gate.name,
        description=gate.description,
        rules=[QualityGateRule.model_validate(rule) for rule in gate.rules],
        created_at=gate.created_at,
        updated_at=gate.updated_at,
    )


def _result_response(result: QualityGateResult) -> QualityGateResultResponse:
    return QualityGateResultResponse(
        id=result.id,
        quality_gate_id=result.quality_gate_id,
        baseline_experiment_id=result.baseline_experiment_id,
        candidate_experiment_id=result.candidate_experiment_id,
        status=result.status,
        comparisons=result.comparisons,
        violations=result.violations,
        warnings=result.warnings,
        evaluated_at=result.evaluated_at,
    )


async def _baseline_response(
    repository: QualityGateRepository, baseline: ExperimentBaseline
) -> BaselineResponse:
    value = await repository.experiment_with_dataset(baseline.experiment_id, baseline.project_id)
    if value is None:
        raise NotFoundError("Baseline experiment")
    return BaselineResponse(
        id=baseline.id,
        project_id=baseline.project_id,
        dataset_id=baseline.dataset_id,
        experiment_id=baseline.experiment_id,
        experiment_name=value[0].name,
        created_at=baseline.created_at,
        updated_at=baseline.updated_at,
    )


@router.post(
    "/projects/{project_id}/experiments/{experiment_id}/baseline",
    response_model=BaselineResponse,
)
async def set_experiment_baseline(
    experiment_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> BaselineResponse:
    baseline = await QualityGateService(session).set_baseline(
        access.project, access.membership, experiment_id, user
    )
    return await _baseline_response(QualityGateRepository(session), baseline)


@router.get("/projects/{project_id}/baseline", response_model=BaselineResponse)
async def get_dataset_baseline(
    access: ProjectAccessDependency,
    session: SessionDependency,
    dataset_id: Annotated[UUID, Query()],
) -> BaselineResponse:
    require_permission(access.membership.role, Permission.QUALITY_GATE_READ)
    repository = QualityGateRepository(session)
    baseline = await repository.baseline(dataset_id, access.project.id)
    if baseline is None:
        raise NotFoundError("Dataset baseline")
    return await _baseline_response(repository, baseline)


@router.get(
    "/projects/{project_id}/experiments/{candidate_id}/comparison",
    response_model=list[MetricComparison],
)
async def compare_experiment(
    candidate_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> list[MetricComparison]:
    require_permission(access.membership.role, Permission.QUALITY_GATE_READ)
    repository = QualityGateRepository(session)
    candidate_value = await repository.experiment_with_dataset(candidate_id, access.project.id)
    if candidate_value is None:
        raise NotFoundError("Candidate experiment")
    candidate, version = candidate_value
    baseline_record = await repository.baseline(version.dataset_id, access.project.id)
    if baseline_record is None:
        raise NotFoundError("Dataset baseline")
    if baseline_record.experiment_id == candidate.id:
        raise ConflictError("Candidate must differ from the baseline")
    baseline_value = await repository.experiment_with_dataset(
        baseline_record.experiment_id, access.project.id
    )
    if baseline_value is None:
        raise NotFoundError("Baseline experiment")
    return compare_metrics(baseline_value[0], candidate)


@router.get("/projects/{project_id}/quality-gates", response_model=list[QualityGateResponse])
async def list_quality_gates(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[QualityGateResponse]:
    require_permission(access.membership.role, Permission.QUALITY_GATE_READ)
    gates = await QualityGateRepository(session).list_gates(access.project.id)
    return [_gate_response(gate) for gate in gates]


@router.post(
    "/projects/{project_id}/quality-gates",
    response_model=QualityGateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quality_gate(
    payload: QualityGateCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> QualityGateResponse:
    gate = await QualityGateService(session).create_gate(
        access.project, access.membership, payload, user
    )
    return _gate_response(gate)


@router.post(
    "/projects/{project_id}/quality-gates/{gate_id}/evaluate",
    response_model=QualityGateResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def evaluate_quality_gate(
    gate_id: UUID,
    payload: QualityGateRunRequest,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> QualityGateResultResponse:
    result = await QualityGateService(session).evaluate(
        access.project,
        access.membership,
        gate_id,
        payload.candidate_experiment_id,
        user,
    )
    return _result_response(result)


@router.get(
    "/projects/{project_id}/experiments/{candidate_id}/quality-gate-results",
    response_model=list[QualityGateResultResponse],
)
async def list_quality_gate_results(
    candidate_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> list[QualityGateResultResponse]:
    require_permission(access.membership.role, Permission.QUALITY_GATE_READ)
    results = await QualityGateRepository(session).results(candidate_id, access.project.id)
    return [_result_response(result) for result in results]
