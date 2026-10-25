import time

import redis
from fastapi import Depends, HTTPException, status

from app.config import settings
from app.security import get_current_key

WINDOW_SECONDS = 60

_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def enforce_rate_limit(key: dict = Depends(get_current_key)) -> dict:
    """Fixed window rate limit: har key ke liye har minute ka counter Redis mein."""
    window = int(time.time()) // WINDOW_SECONDS
    redis_key = f"ratelimit:{key['id']}:{window}"

    count = _redis.incr(redis_key)
    if count == 1:
        # Pehli request is window mein: counter 60 second mein expire ho jaaye
        _redis.expire(redis_key, WINDOW_SECONDS)

    if count > settings.rate_limit_per_minute:
        retry_after = _redis.ttl(redis_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Thoda ruk kar try karo.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )

    return key