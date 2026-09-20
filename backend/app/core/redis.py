import json
from datetime import datetime
from typing import Any, Optional

from redis import asyncio as aioredis

from app.core.config import settings

redis = None


class CacheJSONEncoder(json.JSONEncoder):
    """JSON encoder that tolerates datetime / ObjectId values from Mongo docs."""

    def default(self, obj: Any):
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            from bson import ObjectId

            if isinstance(obj, ObjectId):
                return str(obj)
        except ImportError:  # pragma: no cover
            pass
        return super().default(obj)


def cache_dumps(data: Any) -> str:
    """Serialize a session payload for Redis without crashing on datetimes."""
    return json.dumps(data, cls=CacheJSONEncoder, ensure_ascii=False)


def cache_loads(payload: Any) -> Optional[Any]:
    if payload is None:
        return None
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return json.loads(payload)


async def init_redis():
    """Connect to Redis, but degrade to no-cache mode if it is unreachable."""
    global redis
    try:
        client = await aioredis.from_url(settings.REDIS_URL)
        await client.ping()
        redis = client
    except Exception:
        redis = None


def get_redis():
    return redis
