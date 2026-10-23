import logging
import time
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from agentscope_api.core.config import Settings
from agentscope_api.core.exceptions import RateLimitError

logger = logging.getLogger("agentscope.ingestion")


async def enforce_ingestion_rate_limit(key_id: UUID, settings: Settings) -> None:
    """Use Redis for a fixed-window ingestion limit and fail open on infrastructure failure."""

    minute = int(time.time() // 60)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        key = f"agentscope:ingest:{key_id}:{minute}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 70)
        if count > settings.ingest_rate_limit_per_minute:
            raise RateLimitError
    except RateLimitError:
        raise
    except RedisError:
        logger.warning("ingestion.rate_limit_unavailable")
    finally:
        await redis.aclose()
