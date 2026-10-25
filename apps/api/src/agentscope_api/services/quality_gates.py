from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.exceptions import AppError, ConflictError, NotFoundError
from agentscope_api.models import (
    Experiment,
    ExperimentBaseline,
    ExperimentStatus,
    Membership,
    Project,
    QualityGate,
    QualityGateResult,
    QualityGateStatus,
    User,
)
from agentscope_api.repositories.quality_gates import QualityGateRepository
from agentscope_api.schemas.quality_gates import (
    GateFinding,
    MetricComparison,
    QualityGateCreate,
    QualityGateRule,
    QualityMetric,
)
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission

LOWER_IS_BETTER = {
    "hallucination_rate",
    "average_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "average_cost",
    "total_cost",
    "token_usage",
}

SUPPORTED_METRICS = {
    "pass_rate",
    "average_correctness",
    "hallucination_rate",
    "tool_accuracy",
    "average_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "average_cost",
    "total_cost",
    "token_usage",
}


def _numeric_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, (int, float, str)):
            try:
                result[key] = float(value)
            except ValueError:
                continue
    return result


def compare_metrics(baseline: Experiment, candidate: Experiment) -> list[MetricComparison]:
    left = _numeric_metrics(baseline.metrics)
    right = _numeric_metrics(candidate.metrics)
    comparisons: list[MetricComparison] = []
    for metric in sorted(set(left).intersection(right)):
        if metric not in SUPPORTED_METRICS:
            continue
        baseline_value = left[metric]
        candidate_value = right[metric]
        delta = candidate_value - baseline_value
        percentage = delta / abs(baseline_value) if baseline_value != 0 else None
        direction = "UP" if delta > 0 else "DOWN" if delta < 0 else "UNCHANGED"
        if delta == 0:
            classification = "UNCHANGED"
        elif metric in LOWER_IS_BETTER:
            classification = "IMPROVEMENT" if delta < 0 else "REGRESSION"
        else:
            classification = "IMPROVEMENT" if delta > 0 else "REGRESSION"
        comparisons.append(
            MetricComparison(
                metric=cast(QualityMetric, metric),
                baseline=baseline_value,
                candidate=candidate_value,
                absolute_delta=delta,
                percentage_delta=percentage,
                direction=direction,
                classification=classification,
            )
        )
    return comparisons


class QualityGateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = QualityGateRepository(session)

    async def set_baseline(
        self,
        project: Project,
        membership: Membership,
        experiment_id: UUID,
        user: User,
    ) -> ExperimentBaseline:
        require_permission(membership.role, Permission.QUALITY_GATE_MANAGE)
        value = await self.repository.experiment_with_dataset(experiment_id, project.id)
        if value is None:
            raise NotFoundError("Experiment")
        experiment, version = value
        if experiment.status is not ExperimentStatus.COMPLETED:
            raise ConflictError("Only a completed experiment can become a baseline")
        baseline = await self.repository.baseline(version.dataset_id, project.id)
        if baseline is None:
            baseline = ExperimentBaseline(
                id=uuid4(),
                organization_id=project.organization_id,
                project_id=project.id,
                dataset_id=version.dataset_id,
                experiment_id=experiment.id,
                created_by=user.id,
            )
            self.session.add(baseline)
        else:
            baseline.experiment_id = experiment.id
            baseline.created_by = user.id
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="experiment.baseline_set",
            resource_type="experiment",
            resource_id=experiment.id,
            metadata={"dataset_id": str(version.dataset_id)},
        )
        await self.session.commit()
        return baseline

    async def create_gate(
        self,
        project: Project,
        membership: Membership,
        request: QualityGateCreate,
        user: User,
    ) -> QualityGate:
        require_permission(membership.role, Permission.QUALITY_GATE_MANAGE)
        gate = QualityGate(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            name=request.name,
            description=request.description,
            rules=[rule.model_dump(mode="json") for rule in request.rules],
            created_by=user.id,
        )
        self.session.add(gate)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("A quality gate with this name already exists") from error
        return gate

    async def evaluate(
        self,
        project: Project,
        membership: Membership,
        gate_id: UUID,
        candidate_id: UUID,
        user: User,
    ) -> QualityGateResult:
        require_permission(membership.role, Permission.QUALITY_GATE_MANAGE)
        gate = await self.repository.gate(gate_id, project.id)
        if gate is None:
            raise NotFoundError("Quality gate")
        candidate_value = await self.repository.experiment_with_dataset(candidate_id, project.id)
        if candidate_value is None:
            raise NotFoundError("Candidate experiment")
        candidate, version = candidate_value
        if candidate.status is not ExperimentStatus.COMPLETED:
            raise ConflictError("Candidate experiment must be completed")
        baseline_record = await self.repository.baseline(version.dataset_id, project.id)
        if baseline_record is None:
            raise NotFoundError("Dataset baseline")
        baseline_value = await self.repository.experiment_with_dataset(
            baseline_record.experiment_id, project.id
        )
        if baseline_value is None:
            raise NotFoundError("Baseline experiment")
        baseline = baseline_value[0]
        if baseline.id == candidate.id:
            raise ConflictError("Candidate must differ from the baseline")
        comparisons = compare_metrics(baseline, candidate)
        by_metric = {item.metric: item for item in comparisons}
        violations: list[GateFinding] = []
        warnings: list[GateFinding] = []
        rules = [QualityGateRule.model_validate(rule) for rule in gate.rules]
        for rule in rules:
            comparison = by_metric.get(rule.metric)
            if comparison is None:
                raise AppError(
                    "UNSUPPORTED_GATE_METRIC",
                    f"Metric {rule.metric} is not available in both experiments",
                    status_code=422,
                )
            raw = self._deterioration(rule, comparison)
            if rule.comparison == "relative":
                if comparison.baseline == 0:
                    raise AppError(
                        "UNDEFINED_RELATIVE_COMPARISON",
                        f"Metric {rule.metric} has a zero baseline; use absolute comparison",
                        status_code=422,
                    )
                observed = raw / abs(comparison.baseline)
            else:
                observed = raw
            if observed > rule.threshold:
                finding = GateFinding(
                    metric=rule.metric,
                    message=(
                        f"{rule.metric} deterioration {observed:.6g} exceeds "
                        f"the {rule.threshold:.6g} threshold"
                    ),
                    observed=observed,
                    threshold=rule.threshold,
                    comparison=rule.comparison,
                )
                (violations if rule.severity == "FAIL" else warnings).append(finding)
        result = QualityGateResult(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            quality_gate_id=gate.id,
            baseline_experiment_id=baseline.id,
            candidate_experiment_id=candidate.id,
            status=(
                QualityGateStatus.FAILED
                if violations
                else QualityGateStatus.PASSED_WITH_WARNINGS
                if warnings
                else QualityGateStatus.PASSED
            ),
            comparisons=[item.model_dump(mode="json") for item in comparisons],
            violations=[item.model_dump(mode="json") for item in violations],
            warnings=[item.model_dump(mode="json") for item in warnings],
            rule_snapshot=[rule.model_dump(mode="json") for rule in rules],
            evaluated_at=datetime.now(UTC),
            created_by=user.id,
        )
        self.session.add(result)
        await self.session.commit()
        return result

    @staticmethod
    def _deterioration(rule: QualityGateRule, comparison: MetricComparison) -> float:
        if rule.constraint == "max_increase":
            return max(0.0, comparison.candidate - comparison.baseline)
        if rule.metric in LOWER_IS_BETTER:
            return max(0.0, comparison.candidate - comparison.baseline)
        return max(0.0, comparison.baseline - comparison.candidate)
