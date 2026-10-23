from celery import Celery
from kombu import Queue
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTSCOPE_", extra="ignore")
    redis_url: str = "redis://localhost:6379/0"


settings = WorkerSettings()
celery_app = Celery("agentscope", broker=settings.redis_url, backend=settings.redis_url)
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
)
