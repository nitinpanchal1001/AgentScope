import logging
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]

from agentscope_api.core.config import get_settings

logger = logging.getLogger("agentscope.evaluations")
settings = get_settings()
celery_client = Celery("agentscope-api", broker=settings.redis_url)
celery_client.conf.update(
    broker_connection_timeout=1,
    broker_connection_retry=False,
    task_serializer="json",
    accept_content=["json"],
)


def dispatch_evaluation(result_id: UUID) -> bool:
    try:
        celery_client.send_task(
            "agentscope.evaluate_trace",
            args=[str(result_id)],
            queue="evaluation",
            retry=False,
        )
    except Exception:
        logger.exception("evaluation.dispatch_failed", extra={"result_id": str(result_id)})
        return False
    return True
