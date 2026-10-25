from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.exceptions import ConflictError, NotFoundError
from agentscope_api.models import (
    DatasetItem,
    EvaluationResult,
    EvaluationStatus,
    EvaluatorType,
    EvaluatorVersion,
    Experiment,
    ExperimentEvaluatorVersion,
    ExperimentRun,
    ExperimentRunStatus,
    ExperimentStatus,
    FailureType,
    Membership,
    Project,
    Span,
    SpanType,
    Trace,
    TraceStatus,
    User,
)
from agentscope_api.repositories.experiments import ExperimentRepository
from agentscope_api.repositories.projects import ProjectRepository
from agentscope_api.schemas.experiments import (
    ExperimentAgentSpan,
    ExperimentCreate,
    WorkerExperimentRunCompletion,
    WorkerExperimentRunCompletionResponse,
    WorkerExperimentRunPayload,
)
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission

TERMINAL_RUN_STATUSES = {
    ExperimentRunStatus.COMPLETED,
    ExperimentRunStatus.FAILED,
    ExperimentRunStatus.CANCELLED,
}
TERMINAL_EVALUATION_STATUSES = {
    EvaluationStatus.SUCCESS,
    EvaluationStatus.FAILED,
    EvaluationStatus.SKIPPED,
}
TOOL_EVALUATORS = {
    EvaluatorType.REQUIRED_TOOL,
    EvaluatorType.FORBIDDEN_TOOL,
    EvaluatorType.TOOL_ARGUMENTS,
    EvaluatorType.TOOL_SELECTION,
}


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _failure_type(value: str | None) -> FailureType | None:
    if value is None:
        return None
    try:
        return FailureType(value)
    except ValueError:
        return FailureType.UNKNOWN


class ExperimentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ExperimentRepository(session)

    async def create(
        self,
        project: Project,
        membership: Membership,
        request: ExperimentCreate,
        user: User,
    ) -> Experiment:
        require_permission(membership.role, Permission.EXPERIMENT_MANAGE)
        dataset_value = await self.repository.dataset_version(
            request.dataset_version_id, project.id
        )
        if dataset_value is None:
            raise NotFoundError("Dataset version")
        environment = await ProjectRepository(self.session).get_environment(
            project.id, request.environment_id
        )
        if environment is None:
            raise NotFoundError("Environment")
        evaluator_ids = list(dict.fromkeys(request.evaluator_version_ids))
        if not await self.repository.evaluator_versions_exist(evaluator_ids, project.id):
            raise NotFoundError("Evaluator version")
        items = await self.repository.dataset_items(request.dataset_version_id)
        if not items:
            raise ConflictError("The selected dataset version has no cases")

        experiment = Experiment(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            environment_id=request.environment_id,
            dataset_version_id=request.dataset_version_id,
            name=request.name,
            description=request.description,
            status=ExperimentStatus.PENDING,
            agent_configuration=request.agent.model_dump(mode="json"),
            max_concurrency=request.max_concurrency,
            total_cases=len(items),
            completed_cases=0,
            passed_cases=0,
            failed_cases=0,
            metrics={"total_cases": len(items), "completed": 0},
            cancel_requested=False,
            created_by=user.id,
        )
        links = [
            ExperimentEvaluatorVersion(
                experiment_id=experiment.id,
                evaluator_version_id=evaluator_id,
            )
            for evaluator_id in evaluator_ids
        ]
        runs = [
            ExperimentRun(
                id=uuid4(),
                experiment_id=experiment.id,
                dataset_item_id=item.id,
                ordinal=item.ordinal,
                status=ExperimentRunStatus.PENDING,
                response_metadata={},
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                total_cost=Decimal("0"),
            )
            for item in items
        ]
        self.repository.add_all([experiment, *links, *runs])
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="experiment.created",
            resource_type="experiment",
            resource_id=experiment.id,
            metadata={
                "dataset_version_id": str(request.dataset_version_id),
                "total_cases": len(items),
                "evaluator_count": len(evaluator_ids),
            },
        )
        await self.session.commit()
        return experiment

    async def start(
        self,
        project: Project,
        membership: Membership,
        experiment_id: UUID,
        user: User,
    ) -> list[UUID]:
        require_permission(membership.role, Permission.EXPERIMENT_RUN)
        scoped = await self.repository.get_experiment(experiment_id, project.id)
        if scoped is None:
            raise NotFoundError("Experiment")
        experiment = await self.repository.lock_experiment(experiment_id)
        if experiment is None:
            raise NotFoundError("Experiment")
        if experiment.status is not ExperimentStatus.PENDING:
            raise ConflictError("Only a pending experiment can be started")
        now = datetime.now(UTC)
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = now
        runs = await self.repository.claim_pending_runs(experiment.id, experiment.max_concurrency)
        for run in runs:
            run.status = ExperimentRunStatus.RUNNING
            run.started_at = now
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="experiment.started",
            resource_type="experiment",
            resource_id=experiment.id,
        )
        await self.session.commit()
        return [run.id for run in runs]

    async def cancel(
        self,
        project: Project,
        membership: Membership,
        experiment_id: UUID,
        user: User,
    ) -> Experiment:
        require_permission(membership.role, Permission.EXPERIMENT_RUN)
        scoped = await self.repository.get_experiment(experiment_id, project.id)
        if scoped is None:
            raise NotFoundError("Experiment")
        experiment = await self.repository.lock_experiment(experiment_id)
        if experiment is None:
            raise NotFoundError("Experiment")
        if experiment.status in {
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.CANCELLED,
        }:
            return experiment
        experiment.cancel_requested = True
        experiment.status = ExperimentStatus.CANCELLED
        experiment.completed_at = datetime.now(UTC)
        for run, _ in await self.repository.list_runs(experiment.id):
            if run.status is ExperimentRunStatus.PENDING:
                run.status = ExperimentRunStatus.CANCELLED
                run.completed_at = experiment.completed_at
        await self._aggregate(experiment)
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="experiment.cancelled",
            resource_type="experiment",
            resource_id=experiment.id,
        )
        await self.session.commit()
        return experiment

    async def handle_initial_dispatch_failures(
        self,
        experiment_id: UUID,
        failed_run_ids: list[UUID],
        *,
        all_failed: bool,
    ) -> None:
        if not failed_run_ids:
            return
        experiment = await self.repository.lock_experiment(experiment_id)
        if experiment is None:
            return
        now = datetime.now(UTC)
        if all_failed:
            for run, _ in await self.repository.list_runs(experiment.id):
                if run.status in {
                    ExperimentRunStatus.PENDING,
                    ExperimentRunStatus.RUNNING,
                }:
                    run.status = ExperimentRunStatus.FAILED
                    run.error_type = "DISPATCH_FAILED"
                    run.error_message = "The experiment queue was unavailable"
                    run.completed_at = now
            await self._aggregate(experiment)
            experiment.status = ExperimentStatus.FAILED
            experiment.error_message = "No experiment tasks could be dispatched"
            experiment.completed_at = now
        else:
            for run_id in failed_run_ids:
                failed_run = await self.repository.lock_run(run_id)
                if failed_run is not None and failed_run.status is ExperimentRunStatus.RUNNING:
                    failed_run.status = ExperimentRunStatus.PENDING
                    failed_run.started_at = None
        await self.session.commit()

    async def worker_payload(self, run_id: UUID) -> WorkerExperimentRunPayload:
        value = await self.repository.run_payload(run_id)
        if value is None:
            raise NotFoundError("Experiment run")
        run, experiment, item = value
        agent = experiment.agent_configuration
        return WorkerExperimentRunPayload(
            run_id=run.id,
            status=run.status,
            endpoint=agent["endpoint"],
            timeout_seconds=agent["timeout_seconds"],
            headers_from_env=agent.get("headers_from_env", {}),
            request={
                "input": item.input,
                "context": item.context,
                "configuration": {
                    "provider": agent.get("provider"),
                    "model": agent.get("model"),
                    "prompt_version": agent.get("prompt_version"),
                    "temperature": agent.get("temperature"),
                    "parameters": agent.get("parameters", {}),
                },
                "metadata": {
                    "experiment_id": str(experiment.id),
                    "experiment_run_id": str(run.id),
                    "dataset_item_id": str(item.id),
                    "dataset_item_metadata": item.item_metadata,
                },
            },
        )

    async def complete_invocation(
        self, run_id: UUID, completion: WorkerExperimentRunCompletion
    ) -> WorkerExperimentRunCompletionResponse:
        value = await self.repository.run_payload(run_id)
        if value is None:
            raise NotFoundError("Experiment run")
        run, experiment, item = value
        if run.status in TERMINAL_RUN_STATUSES or run.status is ExperimentRunStatus.EVALUATING:
            return WorkerExperimentRunCompletionResponse(evaluation_result_ids=[], next_run_ids=[])
        now = datetime.now(UTC)
        if experiment.cancel_requested or experiment.status is ExperimentStatus.CANCELLED:
            run.status = ExperimentRunStatus.CANCELLED
            run.completed_at = now
            await self._aggregate(experiment)
            await self.session.commit()
            return WorkerExperimentRunCompletionResponse(evaluation_result_ids=[], next_run_ids=[])

        result_ids: list[UUID] = []
        if completion.status == "FAILED":
            run.status = ExperimentRunStatus.FAILED
            run.error_type = completion.error_type or "AGENT_INVOCATION_FAILED"
            run.error_message = completion.error_message
            run.latency_ms = completion.latency_ms
            run.completed_at = now
        else:
            trace = self._create_trace(experiment, run, item, completion, now)
            self.session.add(trace)
            await self.session.flush()
            self._create_spans(experiment, run, item, trace, completion, now)
            await self.session.flush()
            run.trace_id = trace.id
            run.output = completion.output
            run.response_metadata = completion.metadata
            run.latency_ms = completion.latency_ms
            run.input_tokens = completion.input_tokens
            run.output_tokens = completion.output_tokens
            run.total_tokens = completion.total_tokens
            run.total_cost = completion.total_cost
            evaluator_ids = await self.repository.evaluator_version_ids(experiment.id)
            from agentscope_api.services.evaluations import EvaluationService

            results = await EvaluationService(self.session).prepare_experiment(
                trace,
                run,
                evaluator_ids,
                expected_output=item.expected_output,
                context=item.context,
            )
            result_ids = [result.id for result in results]
            if result_ids:
                run.status = ExperimentRunStatus.EVALUATING
            else:
                run.status = ExperimentRunStatus.COMPLETED
                run.passed = True
                run.completed_at = now

        next_ids = await self._claim_next(experiment, now)
        await self._aggregate(experiment)
        await self.session.commit()
        return WorkerExperimentRunCompletionResponse(
            evaluation_result_ids=result_ids,
            next_run_ids=next_ids,
        )

    async def refresh_run_from_evaluations(self, run_id: UUID) -> None:
        run = await self.repository.lock_run(run_id)
        if run is None or run.status is not ExperimentRunStatus.EVALUATING:
            return
        results = await self.repository.evaluation_results(run.id)
        if not results or any(
            result.status not in TERMINAL_EVALUATION_STATUSES for result in results
        ):
            return
        now = datetime.now(UTC)
        successful = [result for result in results if result.status is EvaluationStatus.SUCCESS]
        if len(successful) != len(results):
            run.status = ExperimentRunStatus.FAILED
            run.passed = False
            run.error_type = "EVALUATION_FAILED"
            run.error_message = "One or more evaluators failed to produce a result"
        else:
            run.status = ExperimentRunStatus.COMPLETED
            run.passed = all(result.passed is True for result in successful)
            scores = [result.score for result in successful if result.score is not None]
            run.evaluation_score = sum(scores, Decimal("0")) / len(scores) if scores else None
        run.completed_at = now
        experiment = await self.repository.lock_experiment(run.experiment_id)
        if experiment is not None:
            await self._aggregate(experiment)

    async def _claim_next(self, experiment: Experiment, now: datetime) -> list[UUID]:
        if experiment.cancel_requested or experiment.status is not ExperimentStatus.RUNNING:
            return []
        runs = await self.repository.claim_pending_runs(experiment.id, 1)
        for run in runs:
            run.status = ExperimentRunStatus.RUNNING
            run.started_at = now
        return [run.id for run in runs]

    def _create_trace(
        self,
        experiment: Experiment,
        run: ExperimentRun,
        item: DatasetItem,
        completion: WorkerExperimentRunCompletion,
        now: datetime,
    ) -> Trace:
        started_at = run.started_at or now
        trace = Trace(
            id=uuid4(),
            external_trace_id=f"experiment:{run.id}",
            organization_id=experiment.organization_id,
            project_id=experiment.project_id,
            environment_id=experiment.environment_id,
            name=f"{experiment.name} / case {run.ordinal}",
            input=item.input,
            output=completion.output,
            status=TraceStatus.SUCCESS,
            started_at=started_at,
            ended_at=now,
            latency_ms=completion.latency_ms,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            total_tokens=completion.total_tokens,
            total_cost=completion.total_cost,
            agent_version=experiment.agent_configuration.get("prompt_version"),
            session_id=str(experiment.id),
            user_identifier=None,
            trace_metadata={
                **completion.metadata,
                "experiment_id": str(experiment.id),
                "experiment_run_id": str(run.id),
                "dataset_item_id": str(item.id),
            },
            tags=["experiment", f"experiment:{experiment.id}"],
            error_type=None,
            error_message=None,
            created_at=now,
        )
        return trace

    def _create_spans(
        self,
        experiment: Experiment,
        run: ExperimentRun,
        item: DatasetItem,
        trace: Trace,
        completion: WorkerExperimentRunCompletion,
        now: datetime,
    ) -> None:
        started_at = run.started_at or now
        spans = completion.spans or [
            ExperimentAgentSpan(
                type=SpanType.AGENT,
                name="agent invocation",
                provider=experiment.agent_configuration.get("provider"),
                model=experiment.agent_configuration.get("model"),
                input=item.input,
                output=completion.output,
                latency_ms=completion.latency_ms,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                total_tokens=completion.total_tokens,
                cost=completion.total_cost,
            )
        ]
        for index, span in enumerate(spans, start=1):
            span_started = started_at
            span_ended = (
                span_started + timedelta(milliseconds=span.latency_ms)
                if span.latency_ms is not None
                else now
            )
            self.session.add(
                Span(
                    id=uuid4(),
                    external_span_id=f"experiment-span:{run.id}:{index}",
                    trace_id=trace.id,
                    pricing_id=None,
                    parent_span_id=None,
                    type=span.type,
                    name=span.name,
                    provider=span.provider,
                    model=span.model,
                    input=span.input,
                    output=span.output,
                    started_at=span_started,
                    ended_at=span_ended,
                    latency_ms=span.latency_ms,
                    input_tokens=span.input_tokens,
                    output_tokens=span.output_tokens,
                    total_tokens=span.total_tokens,
                    cost=span.cost,
                    status=span.status,
                    error_type=_failure_type(span.error_type),
                    error_message=span.error_message,
                    span_metadata=span.metadata,
                    tags=span.tags,
                )
            )

    async def _aggregate(self, experiment: Experiment) -> None:
        rows = await self.repository.list_runs(experiment.id)
        runs = [row[0] for row in rows]
        terminal = [run for run in runs if run.status in TERMINAL_RUN_STATUSES]
        passed = [run for run in terminal if run.passed is True]
        failed = [
            run
            for run in terminal
            if run.status is ExperimentRunStatus.FAILED or run.passed is False
        ]
        experiment.completed_cases = len(terminal)
        experiment.passed_cases = len(passed)
        experiment.failed_cases = len(failed)
        latencies = [run.latency_ms for run in runs if run.latency_ms is not None]
        costs = [run.total_cost for run in runs]
        metrics: dict[str, Any] = {
            "total_cases": experiment.total_cases,
            "completed": len(terminal),
            "passed": len(passed),
            "failed": len(failed),
            "pass_rate": len(passed) / len(terminal) if terminal else 0,
            "total_cost": str(sum(costs, Decimal("0"))),
            "average_cost": str(sum(costs, Decimal("0")) / len(runs)) if runs else "0",
            "token_usage": sum(run.total_tokens for run in runs),
        }
        if latencies:
            metrics.update(
                {
                    "average_latency_ms": sum(latencies) / len(latencies),
                    "p50_latency_ms": _percentile(latencies, 0.50),
                    "p95_latency_ms": _percentile(latencies, 0.95),
                    "p99_latency_ms": _percentile(latencies, 0.99),
                }
            )
        evaluation_rows = (
            await self.session.execute(
                select(EvaluationResult, EvaluatorVersion)
                .join(
                    ExperimentRun,
                    ExperimentRun.id == EvaluationResult.experiment_run_id,
                )
                .join(
                    EvaluatorVersion,
                    EvaluatorVersion.id == EvaluationResult.evaluator_version_id,
                )
                .where(
                    ExperimentRun.experiment_id == experiment.id,
                    EvaluationResult.status == EvaluationStatus.SUCCESS,
                )
            )
        ).all()
        correctness = [
            row[0].score
            for row in evaluation_rows
            if row[1].type is EvaluatorType.CORRECTNESS and row[0].score is not None
        ]
        hallucination = [
            row[0] for row in evaluation_rows if row[1].type is EvaluatorType.HALLUCINATION
        ]
        tool_scores = [
            row[0].score
            for row in evaluation_rows
            if row[1].type in TOOL_EVALUATORS and row[0].score is not None
        ]
        if correctness:
            metrics["average_correctness"] = float(
                sum(correctness, Decimal("0")) / len(correctness)
            )
        if hallucination:
            metrics["hallucination_rate"] = sum(
                result.passed is False for result in hallucination
            ) / len(hallucination)
        if tool_scores:
            metrics["tool_accuracy"] = float(sum(tool_scores, Decimal("0")) / len(tool_scores))
        experiment.metrics = metrics
        if (
            experiment.status is ExperimentStatus.RUNNING
            and len(terminal) == experiment.total_cases
        ):
            experiment.status = ExperimentStatus.COMPLETED
            experiment.completed_at = datetime.now(UTC)
