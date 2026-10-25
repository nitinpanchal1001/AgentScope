from typing import Literal

from celery import Celery  # type: ignore[import-untyped]
from kombu import Queue  # type: ignore[import-untyped]
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTSCOPE_", extra="ignore")
    environment: Literal["development", "test", "staging", "production"] = "development"
    redis_url: str = "redis://localhost:6379/0"
    worker_api_url: str = "http://localhost:8000"
    worker_api_key: str = "development-only-worker-key-change-me"
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    experiment_allow_http: bool = False
    experiment_allow_private_endpoints: bool = False
    experiment_allowed_hosts: list[str] = []
    experiment_max_response_bytes: int = Field(default=2_000_000, ge=1_000, le=10_000_000)
    notification_signing_secret: str = "development-notification-signing-secret"  # noqa: S105
    notification_allow_http: bool = False
    notification_allow_private_endpoints: bool = False
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from: str = "alerts@agentscope.local"

    @model_validator(mode="after")
    def validate_production_security(self) -> "WorkerSettings":
        if self.environment != "production":
            return self
        forbidden = ("development", "change-me")
        if len(self.worker_api_key) < 32 or any(
            marker in self.worker_api_key.lower() for marker in forbidden
        ):
            raise ValueError("AGENTSCOPE_WORKER_API_KEY must be changed in production")
        if len(self.notification_signing_secret) < 32 or any(
            marker in self.notification_signing_secret.lower() for marker in forbidden
        ):
            raise ValueError("AGENTSCOPE_NOTIFICATION_SIGNING_SECRET must be changed in production")
        if self.experiment_allow_http or self.experiment_allow_private_endpoints:
            raise ValueError("production experiment endpoint protections cannot be disabled")
        if self.notification_allow_http or self.notification_allow_private_endpoints:
            raise ValueError("production webhook endpoint protections cannot be disabled")
        if not self.redis_url.startswith("rediss://"):
            raise ValueError("production Redis must use TLS (rediss://)")
        return self


settings = WorkerSettings()
celery_app = Celery(
    "agentscope",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["agentscope_worker.tasks"],
)
celery_app.conf.update(
    task_queues=tuple(
        Queue(name)
        for name in (
            "evaluation",
            "experiment",
            "replay",
            "failure_analysis",
            "analytics",
            "alerts",
            "maintenance",
        )
    ),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "evaluate-alert-rules-every-minute": {
            "task": "agentscope.evaluate_alerts",
            "schedule": 60.0,
            "options": {"queue": "alerts"},
        },
        "expire-telemetry-daily": {
            "task": "agentscope.expire_telemetry",
            "schedule": 86_400.0,
            "options": {"queue": "maintenance"},
        },
    },
)
