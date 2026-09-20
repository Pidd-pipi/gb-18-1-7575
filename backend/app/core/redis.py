from redis import asyncio as aioredis
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

redis = None


async def init_redis():
    """Redis 仅作缓存，连接失败时降级为直连数据库，不影响主流程。"""
    global redis
    try:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        redis = client
    except Exception as e:
        logger.warning(f"Redis 连接失败，缓存已禁用: {e}")
        redis = None


def get_redis():
    return redis
