import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Response, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    ProjectAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AuthenticationError
from agentscope_api.models import AlertEvent, AlertRule
from agentscope_api.repositories.alerts import AlertRepository
from agentscope_api.schemas.alerts import (
    AlertDeliveryResult,
    AlertEvaluationResponse,
    AlertEventResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
    PendingAlertDelivery,
    display_channel_target,
)
from agentscope_api.services.alerts import AlertService
from agentscope_api.services.authorization import Permission, require_permission

router = APIRouter(tags=["Alerts"])
internal_router = APIRouter(prefix="/internal/v1", tags=["Internal alert worker"])


def _rule(value: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=value.id,
        project_id=value.project_id,
        organization_id=value.organization_id,
        name=value.name,
        environment_id=value.environment_id,
        metric=value.metric,
        operator=value.operator,
        threshold=value.threshold,
        window_minutes=value.window_minutes,
        severity=value.severity,
        enabled=value.enabled,
        channel=value.channel,
        channel_target=display_channel_target(value.channel, value.channel_target),
        cooldown_minutes=value.cooldown_minutes,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _event(value: AlertEvent) -> AlertEventResponse:
    return AlertEventResponse.model_validate(value, from_attributes=True)


def _pending(value: AlertEvent) -> PendingAlertDelivery:
    return PendingAlertDelivery(
        **_event(value).model_dump(),
        channel_target=value.channel_target,
    )


def _require_worker_key(supplied: str | None, expected: str) -> None:
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise AuthenticationError("Invalid alert worker credential")


@router.post(
    "/projects/{project_id}/alert-rules",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_alert_rule(
    payload: AlertRuleCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> AlertRuleResponse:
    value = await AlertService(session).create(access.project, access.membership, payload, user)
    return _rule(value)


@router.get("/projects/{project_id}/alert-rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[AlertRuleResponse]:
    require_permission(access.membership.role, Permission.ALERT_READ)
    return [_rule(value) for value in await AlertRepository(session).rules(access.project.id)]


@router.put("/projects/{project_id}/alert-rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: UUID,
    payload: AlertRuleUpdate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> AlertRuleResponse:
    value = await AlertService(session).update(
        access.project, access.membership, rule_id, payload, user
    )
    return _rule(value)


@router.delete(
    "/projects/{project_id}/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_alert_rule(
    rule_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    user: CurrentUser,
) -> Response:
    await AlertService(session).delete(access.project, access.membership, rule_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/alerts", response_model=list[AlertEventResponse])
async def list_alert_events(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[AlertEventResponse]:
    require_permission(access.membership.role, Permission.ALERT_READ)
    return [_event(value) for value in await AlertRepository(session).events(access.project.id)]


@internal_router.post(
    "/alerts/evaluate", response_model=AlertEvaluationResponse, include_in_schema=False
)
async def evaluate_alerts(
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> AlertEvaluationResponse:
    _require_worker_key(worker_key, settings.worker_api_key)
    evaluated, triggered = await AlertService(session).evaluate_all()
    return AlertEvaluationResponse(
        evaluated_rules=evaluated,
        triggered=[_pending(value) for value in triggered],
    )


@internal_router.post(
    "/alerts/{event_id}/delivery", response_model=AlertEventResponse, include_in_schema=False
)
async def record_alert_delivery(
    event_id: UUID,
    payload: AlertDeliveryResult,
    session: SessionDependency,
    settings: SettingsDependency,
    worker_key: Annotated[str | None, Header(alias="X-AgentScope-Worker-Key")] = None,
) -> AlertEventResponse:
    _require_worker_key(worker_key, settings.worker_api_key)
    return _event(await AlertService(session).record_delivery(event_id, payload))
