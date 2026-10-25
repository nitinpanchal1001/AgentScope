import logging
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]

from agentscope_api.core.config import get_settings

logger = logging.getLogger("agentscope.failures")
settings = get_settings()
celery_client = Celery("agentscope-api", broker=settings.redis_url)
celery_client.conf.update(
    broker_connection_timeout=1,
    broker_connection_retry=False,
    task_serializer="json",
    accept_content=["json"],
)


def dispatch_failure_analysis(trace_id: UUID) -> bool:
    try:
        celery_client.send_task(
            "agentscope.analyze_failure",
            args=[str(trace_id)],
            queue="failure_analysis",
            retry=False,
        )
    except Exception:
        logger.exception("failure_analysis.dispatch_failed", extra={"trace_id": str(trace_id)})
        return False
    return True
