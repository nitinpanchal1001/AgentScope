import logging
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]

from agentscope_api.core.config import get_settings

logger = logging.getLogger("agentscope.experiments")
settings = get_settings()
celery_client = Celery("agentscope-api", broker=settings.redis_url)
celery_client.conf.update(
    broker_connection_timeout=1,
    broker_connection_retry=False,
    task_serializer="json",
    accept_content=["json"],
)


def dispatch_experiment_run(run_id: UUID) -> bool:
    try:
        celery_client.send_task(
            "agentscope.execute_experiment_run",
            args=[str(run_id)],
            queue="experiment",
            retry=False,
        )
    except Exception:
        logger.exception("experiment.dispatch_failed", extra={"run_id": str(run_id)})
        return False
    return True
