from app.core.config import settings
from redis import asyncio as aioredis
from fastapi.encoders import jsonable_encoder
import json


redis_url = settings.REDIS_URL
if redis_url.startswith("rediss://"):
    redis_client = aioredis.from_url(
        redis_url,
        ssl_cert_reqs=None,
        decode_responses=True,
    )
else:
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
try:
    print(redis_client.ping())
except Exception as e:
    print(f"Redis connection failed: {e}")


async def caching(key: str):
    value = await redis_client.get(key)
    if value:
        return json.loads(value)
    return None


async def cached(key: str, data, ttl: int = 60):
    data = data.model_dump(exclude_none=True, exclude_defaults=True)
    payload = jsonable_encoder(data)
    await redis_client.set(key, json.dumps(payload), ex=ttl)
    return payload


async def cache_invalidation(user_id: int):
    cursor = 0
    pattern = f"profile:{user_id}:*"
    delete = False
    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=1000)
        if keys:
            await redis_client.delete(*keys)
            delete = True
        if cursor == 0 or cursor == b"0":
            break
    return delete
