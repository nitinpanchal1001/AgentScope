import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.exceptions import ConflictError, NotFoundError
from agentscope_api.models import (
    EvaluationResult,
    EvaluationSource,
    EvaluationStatus,
    Evaluator,
    EvaluatorVersion,
    ExperimentRun,
    Membership,
    ProductionEvaluationBinding,
    Project,
    Span,
    Trace,
    User,
)
from agentscope_api.repositories.evaluations import EvaluationRepository
from agentscope_api.repositories.projects import ProjectRepository
from agentscope_api.schemas.evaluations import (
    EvaluationBindingCreate,
    EvaluationBindingUpdate,
    EvaluationFilter,
    EvaluatorCreate,
    EvaluatorVersionCreate,
    WorkerEvaluationCompletion,
    WorkerEvaluationPayload,
)
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission


def _sampled(trace_id: UUID, binding_id: UUID, sample_rate: Decimal) -> bool:
    digest = hashlib.sha256(f"{trace_id}:{binding_id}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    return value < float(sample_rate)


def _matches_filters(trace: Trace, filters: dict[str, Any]) -> bool:
    try:
        parsed = EvaluationFilter.model_validate(filters)
    except ValidationError:
        return False
    if parsed.statuses and trace.status not in parsed.statuses:
        return False
    if parsed.tags_any and not set(parsed.tags_any).intersection(trace.tags):
        return False
    if parsed.agent_versions and trace.agent_version not in parsed.agent_versions:
        return False
    return True


def _trace_payload(trace: Trace, spans: list[Span]) -> dict[str, Any]:
    return {
        "id": str(trace.id),
        "external_trace_id": trace.external_trace_id,
        "name": trace.name,
        "status": trace.status.value,
        "latency_ms": trace.latency_ms,
        "input_tokens": trace.input_tokens,
        "output_tokens": trace.output_tokens,
        "total_tokens": trace.total_tokens,
        "total_cost": str(trace.total_cost),
        "agent_version": trace.agent_version,
        "metadata": trace.trace_metadata,
        "tags": trace.tags,
        "spans": [
            {
                "id": str(span.id),
                "external_span_id": span.external_span_id,
                "type": span.type.value,
                "name": span.name,
                "provider": span.provider,
                "model": span.model,
                "input": span.input,
                "output": span.output,
                "latency_ms": span.latency_ms,
                "cost": str(span.cost),
                "status": span.status.value,
                "metadata": span.span_metadata,
                "tags": span.tags,
            }
            for span in spans
        ],
    }


class EvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = EvaluationRepository(session)

    async def create_evaluator(
        self,
        project: Project,
        membership: Membership,
        request: EvaluatorCreate,
        user: User,
    ) -> tuple[Evaluator, list[EvaluatorVersion]]:
        require_permission(membership.role, Permission.EVALUATOR_MANAGE)
        evaluator = Evaluator(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            name=request.name,
            description=request.description,
            enabled=True,
            created_by=user.id,
        )
        version = self._new_version(evaluator.id, 1, request.version, user.id)
        self.repository.add_all([evaluator, version])
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="evaluator.created",
            resource_type="evaluator",
            resource_id=evaluator.id,
            metadata={"type": version.type.value},
        )
        try:
            await self.session.commit()
        except Exception as error:
            await self.session.rollback()
            raise ConflictError("An evaluator with this name already exists") from error
        return evaluator, [version]

    async def create_version(
        self,
        project: Project,
        membership: Membership,
        evaluator_id: UUID,
        request: EvaluatorVersionCreate,
        user: User,
    ) -> EvaluatorVersion:
        require_permission(membership.role, Permission.EVALUATOR_MANAGE)
        evaluator = await self.repository.get_evaluator(evaluator_id, project.id)
        if evaluator is None:
            raise NotFoundError("Evaluator")
        await self.session.execute(
            select(Evaluator.id).where(Evaluator.id == evaluator_id).with_for_update()
        )
        version_number = await self.repository.next_version(evaluator_id)
        version = self._new_version(evaluator_id, version_number, request, user.id)
        self.repository.add_all([version])
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="evaluator.version_created",
            resource_type="evaluator_version",
            resource_id=version.id,
            metadata={"evaluator_id": str(evaluator_id), "version": version_number},
        )
        await self.session.commit()
        return version

    async def set_evaluator_enabled(
        self,
        project: Project,
        membership: Membership,
        evaluator_id: UUID,
        enabled: bool,
        user: User,
    ) -> Evaluator:
        require_permission(membership.role, Permission.EVALUATOR_MANAGE)
        evaluator = await self.repository.get_evaluator(evaluator_id, project.id)
        if evaluator is None:
            raise NotFoundError("Evaluator")
        evaluator.enabled = enabled
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="evaluator.enabled" if enabled else "evaluator.disabled",
            resource_type="evaluator",
            resource_id=evaluator.id,
        )
        await self.session.commit()
        return evaluator

    async def create_binding(
        self,
        project: Project,
        membership: Membership,
        request: EvaluationBindingCreate,
        user: User,
    ) -> ProductionEvaluationBinding:
        require_permission(membership.role, Permission.EVALUATOR_MANAGE)
        environment = await ProjectRepository(self.session).get_environment(
            project.id, request.environment_id
        )
        if environment is None:
            raise NotFoundError("Environment")
        if await self.repository.get_version(request.evaluator_version_id, project.id) is None:
            raise NotFoundError("Evaluator version")
        EvaluationFilter.model_validate(request.filters)
        binding = ProductionEvaluationBinding(
            id=uuid4(),
            project_id=project.id,
            environment_id=request.environment_id,
            evaluator_version_id=request.evaluator_version_id,
            enabled=request.enabled,
            sample_rate=request.sample_rate,
            threshold=request.threshold,
            filters=request.filters,
            created_by=user.id,
        )
        self.repository.add_all([binding])
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="evaluation_binding.created",
            resource_type="production_evaluation_binding",
            resource_id=binding.id,
        )
        try:
            await self.session.commit()
        except Exception as error:
            await self.session.rollback()
            raise ConflictError(
                "This evaluator version is already bound to the environment"
            ) from error
        return binding

    async def update_binding(
        self,
        project: Project,
        membership: Membership,
        binding_id: UUID,
        request: EvaluationBindingUpdate,
        user: User,
    ) -> ProductionEvaluationBinding:
        require_permission(membership.role, Permission.EVALUATOR_MANAGE)
        binding = await self.repository.get_binding(binding_id, project.id)
        if binding is None:
            raise NotFoundError("Evaluation binding")
        if request.sample_rate is not None:
            binding.sample_rate = request.sample_rate
        if "threshold" in request.model_fields_set:
            binding.threshold = request.threshold
        if request.filters is not None:
            EvaluationFilter.model_validate(request.filters)
            binding.filters = request.filters
        if request.enabled is not None:
            binding.enabled = request.enabled
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="evaluation_binding.updated",
            resource_type="production_evaluation_binding",
            resource_id=binding.id,
        )
        await self.session.commit()
        return binding

    async def prepare_production(self, trace: Trace) -> list[UUID]:
        result_ids: list[UUID] = []
        for binding, version in await self.repository.active_bindings_for_trace(trace):
            if not _sampled(trace.id, binding.id, binding.sample_rate):
                continue
            if not _matches_filters(trace, binding.filters):
                continue
            result = await self._prepare_result(
                trace,
                version,
                EvaluationSource.PRODUCTION,
                threshold=binding.threshold,
            )
            if result is not None:
                result_ids.append(result.id)
        return result_ids

    async def prepare_manual(
        self,
        project: Project,
        membership: Membership,
        trace_id: UUID,
        version_ids: list[UUID],
    ) -> list[EvaluationResult]:
        require_permission(membership.role, Permission.EVALUATION_RUN)
        trace = await self.session.scalar(
            select(Trace).where(Trace.id == trace_id, Trace.project_id == project.id)
        )
        if trace is None:
            raise NotFoundError("Trace")
        results: list[EvaluationResult] = []
        for version_id in dict.fromkeys(version_ids):
            value = await self.repository.get_version(version_id, project.id)
            if value is None:
                raise NotFoundError("Evaluator version")
            result = await self._prepare_result(trace, value[0], EvaluationSource.MANUAL)
            if result is not None:
                results.append(result)
        await self.session.commit()
        return results

    async def worker_payload(self, result_id: UUID) -> WorkerEvaluationPayload:
        value = await self.repository.worker_payload(result_id)
        if value is None:
            raise NotFoundError("Evaluation result")
        result, trace, version, spans = value
        if result.status is EvaluationStatus.PENDING:
            result.status = EvaluationStatus.RUNNING
            result.started_at = datetime.now(UTC)
            await self.session.commit()
        return WorkerEvaluationPayload(
            result_id=result.id,
            status=result.status,
            evaluator_type=version.type,
            input=trace.input,
            output=trace.output,
            expected_output=result.result_metadata.get(
                "expected_output", version.configuration.get("expected_output")
            ),
            context=result.result_metadata.get("context", version.configuration.get("context")),
            trace=_trace_payload(trace, spans),
            configuration=version.configuration,
            threshold=result.threshold,
            provider=version.provider,
            model=version.model,
            rubric=version.rubric,
        )

    async def complete(
        self, result_id: UUID, completion: WorkerEvaluationCompletion
    ) -> EvaluationResult:
        value = await self.repository.worker_payload(result_id)
        if value is None:
            raise NotFoundError("Evaluation result")
        result = value[0]
        if result.status in {EvaluationStatus.SUCCESS, EvaluationStatus.FAILED}:
            return result
        result.status = completion.status
        result.score = completion.score
        result.passed = completion.passed
        result.label = completion.label
        result.reason = completion.reason
        result.evidence = completion.evidence
        result.result_metadata = completion.metadata
        result.error_type = completion.error_type
        result.error_message = completion.error_message
        result.completed_at = datetime.now(UTC)
        await self.repository.refresh_trace_score(result.trace_id)
        if result.experiment_run_id is not None:
            from agentscope_api.services.experiments import ExperimentService

            await ExperimentService(self.session).refresh_run_from_evaluations(
                result.experiment_run_id
            )
        from agentscope_api.services.replays import ReplayService

        await ReplayService(self.session).refresh_from_evaluations(result.trace_id)
        await self.session.commit()
        return result

    async def prepare_experiment(
        self,
        trace: Trace,
        run: ExperimentRun,
        version_ids: list[UUID],
        *,
        expected_output: Any,
        context: Any,
    ) -> list[EvaluationResult]:
        results: list[EvaluationResult] = []
        for version_id in version_ids:
            value = await self.repository.get_version(version_id, trace.project_id)
            if value is None:
                raise NotFoundError("Evaluator version")
            result = await self._prepare_result(
                trace,
                value[0],
                EvaluationSource.EXPERIMENT,
                experiment_run_id=run.id,
                result_metadata={
                    "expected_output": expected_output,
                    "context": context,
                },
            )
            if result is not None:
                results.append(result)
        return results

    async def prepare_replay(
        self, original_trace: Trace, replay_trace: Trace
    ) -> list[EvaluationResult]:
        original_results = await self.repository.list_results_for_trace(
            original_trace.id, original_trace.project_id
        )
        results: list[EvaluationResult] = []
        for original, version, _ in original_results:
            result = await self._prepare_result(
                replay_trace,
                version,
                EvaluationSource.REPLAY,
                threshold=original.threshold,
                result_metadata=original.result_metadata,
            )
            if result is not None:
                results.append(result)
        return results

    async def _prepare_result(
        self,
        trace: Trace,
        version: EvaluatorVersion,
        source: EvaluationSource,
        *,
        threshold: Decimal | None = None,
        experiment_run_id: UUID | None = None,
        result_metadata: dict[str, Any] | None = None,
    ) -> EvaluationResult | None:
        existing = await self.repository.existing_result(
            trace_id=trace.id,
            evaluator_version_id=version.id,
            source=source,
        )
        if existing is not None:
            return None
        result = EvaluationResult(
            id=uuid4(),
            organization_id=trace.organization_id,
            project_id=trace.project_id,
            environment_id=trace.environment_id,
            trace_id=trace.id,
            experiment_run_id=experiment_run_id,
            evaluator_version_id=version.id,
            source=source,
            status=EvaluationStatus.PENDING,
            threshold=threshold if threshold is not None else version.threshold,
            evidence=[],
            result_metadata=result_metadata or {},
            created_at=datetime.now(UTC),
        )
        self.repository.add_all([result])
        await self.session.flush()
        return result

    @staticmethod
    def _new_version(
        evaluator_id: UUID,
        version_number: int,
        request: EvaluatorVersionCreate,
        user_id: UUID,
    ) -> EvaluatorVersion:
        return EvaluatorVersion(
            id=uuid4(),
            evaluator_id=evaluator_id,
            version=version_number,
            type=request.type,
            configuration=request.configuration,
            threshold=request.threshold,
            provider=request.provider,
            model=request.model,
            rubric=request.rubric,
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
