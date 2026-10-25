import logging
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]

from agentscope_api.core.config import get_settings

logger = logging.getLogger("agentscope.replays")
settings = get_settings()
celery_client = Celery("agentscope-api", broker=settings.redis_url)
celery_client.conf.update(
    broker_connection_timeout=1,
    broker_connection_retry=False,
    task_serializer="json",
    accept_content=["json"],
)


def dispatch_replay(replay_id: UUID) -> bool:
    try:
        celery_client.send_task(
            "agentscope.execute_replay",
            args=[str(replay_id)],
            queue="replay",
            retry=False,
        )
    except Exception:
        logger.exception("replay.dispatch_failed", extra={"replay_id": str(replay_id)})
        return False
    return True
