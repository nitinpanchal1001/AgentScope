from datetime import datetime
from decimal import Decimal
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from agentscope_api.models import (
    AlertEventStatus,
    AlertMetric,
    AlertOperator,
    AlertSeverity,
    NotificationChannel,
)


class AlertRuleValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    environment_id: UUID | None = None
    metric: AlertMetric
    operator: AlertOperator
    threshold: Decimal
    window_minutes: int = Field(default=15, ge=1, le=10_080)
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True
    channel: NotificationChannel
    channel_target: str = Field(min_length=3, max_length=2000)
    cooldown_minutes: int = Field(default=30, ge=1, le=43_200)

    @model_validator(mode="after")
    def validate_channel_target(self) -> "AlertRuleValues":
        if self.channel is NotificationChannel.EMAIL:
            TypeAdapter(EmailStr).validate_python(self.channel_target)
        else:
            parsed = urlsplit(self.channel_target)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("webhook channel_target must be an absolute HTTP(S) URL")
        return self


class AlertRuleCreate(AlertRuleValues):
    pass


class AlertRuleUpdate(AlertRuleValues):
    pass


class AlertRuleResponse(AlertRuleValues):
    id: UUID
    project_id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


class AlertEventResponse(BaseModel):
    id: UUID
    rule_id: UUID | None
    project_id: UUID
    environment_id: UUID | None
    rule_name: str
    metric: AlertMetric
    operator: AlertOperator
    observed_value: Decimal
    threshold: Decimal
    severity: AlertSeverity
    channel: NotificationChannel
    status: AlertEventStatus
    window_started_at: datetime
    window_ended_at: datetime
    triggered_at: datetime
    delivered_at: datetime | None
    delivery_attempts: int
    last_error: str | None


class PendingAlertDelivery(AlertEventResponse):
    channel_target: str


class AlertEvaluationResponse(BaseModel):
    evaluated_rules: int
    triggered: list[PendingAlertDelivery]


class AlertDeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivered: bool
    error: Annotated[str | None, StringConstraints(max_length=2000)] = None


def display_channel_target(channel: NotificationChannel, target: str) -> str:
    if channel is NotificationChannel.EMAIL:
        return target
    parsed = urlsplit(target)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
