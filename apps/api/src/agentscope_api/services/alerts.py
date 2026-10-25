from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.exceptions import NotFoundError
from agentscope_api.models import (
    AlertEvent,
    AlertEventStatus,
    AlertMetric,
    AlertOperator,
    AlertRule,
    FailureRecord,
    Membership,
    Project,
    Span,
    SpanType,
    Trace,
    TraceStatus,
    User,
)
from agentscope_api.repositories.alerts import AlertRepository
from agentscope_api.repositories.analytics import AnalyticsRepository
from agentscope_api.repositories.projects import ProjectRepository
from agentscope_api.schemas.alerts import AlertDeliveryResult, AlertRuleValues
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission


def threshold_matches(operator: AlertOperator, value: Decimal, threshold: Decimal) -> bool:
    return {
        AlertOperator.GREATER_THAN: value > threshold,
        AlertOperator.GREATER_THAN_OR_EQUAL: value >= threshold,
        AlertOperator.LESS_THAN: value < threshold,
        AlertOperator.LESS_THAN_OR_EQUAL: value <= threshold,
    }[operator]


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AlertRepository(session)

    async def create(
        self,
        project: Project,
        membership: Membership,
        payload: AlertRuleValues,
        user: User,
    ) -> AlertRule:
        require_permission(membership.role, Permission.ALERT_MANAGE)
        await self._validate_environment(project.id, payload.environment_id)
        rule = AlertRule(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            created_by=user.id,
            **payload.model_dump(),
        )
        self.session.add(rule)
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="alert_rule.created",
            resource_type="alert_rule",
            resource_id=rule.id,
            metadata={"metric": rule.metric.value, "channel": rule.channel.value},
        )
        await self.session.commit()
        return rule

    async def update(
        self,
        project: Project,
        membership: Membership,
        rule_id: UUID,
        payload: AlertRuleValues,
        user: User,
    ) -> AlertRule:
        require_permission(membership.role, Permission.ALERT_MANAGE)
        rule = await self.repository.rule(rule_id, project.id)
        if rule is None:
            raise NotFoundError("Alert rule")
        await self._validate_environment(project.id, payload.environment_id)
        for key, value in payload.model_dump().items():
            setattr(rule, key, value)
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="alert_rule.updated",
            resource_type="alert_rule",
            resource_id=rule.id,
            metadata={"metric": rule.metric.value, "enabled": rule.enabled},
        )
        await self.session.commit()
        return rule

    async def delete(
        self,
        project: Project,
        membership: Membership,
        rule_id: UUID,
        user: User,
    ) -> None:
        require_permission(membership.role, Permission.ALERT_MANAGE)
        rule = await self.repository.rule(rule_id, project.id)
        if rule is None:
            raise NotFoundError("Alert rule")
        await self.session.delete(rule)
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="alert_rule.deleted",
            resource_type="alert_rule",
            resource_id=rule.id,
            metadata={"metric": rule.metric.value},
        )
        await self.session.commit()

    async def evaluate_all(self, now: datetime | None = None) -> tuple[int, list[AlertEvent]]:
        ended_at = now or datetime.now(UTC)
        rules = await self.repository.enabled_rules()
        triggered: list[AlertEvent] = []
        for rule in rules:
            started_at = ended_at - timedelta(minutes=rule.window_minutes)
            value = await self._metric_value(rule, started_at, ended_at)
            if value is None or not threshold_matches(rule.operator, value, rule.threshold):
                continue
            latest = await self.repository.latest_event(rule.id)
            if latest is not None:
                latest_triggered = latest.triggered_at
                if latest_triggered.tzinfo is None:
                    latest_triggered = latest_triggered.replace(tzinfo=UTC)
                if latest_triggered > ended_at - timedelta(minutes=rule.cooldown_minutes):
                    continue
            bucket = int(ended_at.timestamp()) // (rule.window_minutes * 60)
            deduplication_key = f"{rule.id}:{bucket}"
            if await self.repository.deduplication_exists(deduplication_key):
                continue
            event = AlertEvent(
                id=uuid4(),
                organization_id=rule.organization_id,
                project_id=rule.project_id,
                rule_id=rule.id,
                environment_id=rule.environment_id,
                rule_name=rule.name,
                metric=rule.metric,
                operator=rule.operator,
                observed_value=value,
                threshold=rule.threshold,
                severity=rule.severity,
                channel=rule.channel,
                channel_target=rule.channel_target,
                status=AlertEventStatus.PENDING,
                deduplication_key=deduplication_key,
                window_started_at=started_at,
                window_ended_at=ended_at,
                triggered_at=ended_at,
                delivered_at=None,
                delivery_attempts=0,
                last_error=None,
            )
            self.session.add(event)
            triggered.append(event)
        await self.session.commit()
        return len(rules), triggered

    async def record_delivery(self, event_id: UUID, payload: AlertDeliveryResult) -> AlertEvent:
        event = await self.repository.event(event_id)
        if event is None:
            raise NotFoundError("Alert event")
        event.delivery_attempts += 1
        event.last_error = payload.error
        if payload.delivered:
            event.status = AlertEventStatus.DELIVERED
            event.delivered_at = datetime.now(UTC)
        else:
            event.status = AlertEventStatus.FAILED
        await self.session.commit()
        return event

    async def _validate_environment(self, project_id: UUID, environment_id: UUID | None) -> None:
        if environment_id is None:
            return
        environment = await ProjectRepository(self.session).get_environment(
            project_id, environment_id
        )
        if environment is None:
            raise NotFoundError("Environment")

    async def _metric_value(
        self, rule: AlertRule, started_at: datetime, ended_at: datetime
    ) -> Decimal | None:
        analytics = await AnalyticsRepository(self.session).summary(
            project_id=rule.project_id,
            environment_id=rule.environment_id,
            started_after=started_at,
            started_before=ended_at,
        )
        total = int(analytics["total_traces"])
        if total == 0:
            return None
        if rule.metric is AlertMetric.ERROR_RATE:
            return Decimal(int(analytics["error_traces"])) / Decimal(total) * Decimal(100)
        if rule.metric is AlertMetric.P95_LATENCY_MS:
            value = analytics["p95_latency_ms"]
            return Decimal(str(value)) if value is not None else None
        if rule.metric is AlertMetric.AVERAGE_COST:
            return Decimal(str(analytics["total_cost"])) / Decimal(total)
        if rule.metric is AlertMetric.EVALUATION_SCORE:
            value = analytics["average_evaluation_score"]
            return Decimal(str(value)) if value is not None else None
        trace_filters = [
            Trace.project_id == rule.project_id,
            Trace.started_at >= started_at,
            Trace.started_at < ended_at,
        ]
        if rule.environment_id is not None:
            trace_filters.append(Trace.environment_id == rule.environment_id)
        if rule.metric is AlertMetric.HALLUCINATION_RATE:
            count = await self.session.scalar(
                select(func.count(FailureRecord.id))
                .join(Trace, Trace.id == FailureRecord.trace_id)
                .where(*trace_filters, FailureRecord.failure_type == "HALLUCINATION")
            )
            return Decimal(int(count or 0)) / Decimal(total) * Decimal(100)
        row = (
            await self.session.execute(
                select(
                    func.count(Span.id),
                    func.sum(case((Span.status == TraceStatus.ERROR, 1), else_=0)),
                )
                .join(Trace, Trace.id == Span.trace_id)
                .where(*trace_filters, Span.type == SpanType.TOOL)
            )
        ).one()
        tool_total = int(row[0] or 0)
        if tool_total == 0:
            return None
        return Decimal(int(row[1] or 0)) / Decimal(tool_total) * Decimal(100)
