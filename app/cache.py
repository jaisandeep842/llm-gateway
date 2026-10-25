import hashlib
import json

import redis

from app.config import settings
from app.schemas import ChatRequest, ChatResponse

_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def is_cacheable(req: ChatRequest) -> bool:
    """Sirf temperature 0 wali requests cache hongi, kyunki wahan answer deterministic hota hai."""
    return req.temperature == 0


def make_cache_key(req: ChatRequest) -> str:
    """Model, messages aur max_tokens se SHA-256 hash banata hai."""
    payload = {
        "model": settings.groq_model,
        "messages": [m.model_dump() for m in req.messages],
        "max_tokens": req.max_tokens,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "cache:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(key: str) -> ChatResponse | None:
    raw = _redis.get(key)
    if raw is None:
        return None
    return ChatResponse.model_validate_json(raw)


def set_cached(key: str, resp: ChatResponse) -> None:
    _redis.set(key, resp.model_dump_json(), ex=settings.cache_ttl_seconds)