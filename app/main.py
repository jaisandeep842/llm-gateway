import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response

from app.cache import get_cached, is_cacheable, make_cache_key, set_cached
from app.db import get_db, init_db
from app.providers.groq import GroqError, chat_completion
from app.ratelimit import enforce_rate_limit
from app.routes.admin import router as admin_router
from app.routes.usage import router as usage_router
from app.schemas import ChatRequest, ChatResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LLM Gateway", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(usage_router)


def log_usage(
    key_id: int,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    cache_hit: int,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO usage_logs
                (api_key_id, model, prompt_tokens, completion_tokens, latency_ms, cache_hit)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key_id, model, prompt_tokens, completion_tokens, latency_ms, cache_hit),
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    response: Response,
    key: dict = Depends(enforce_rate_limit),
):
    started = time.perf_counter()
    cacheable = is_cacheable(req)
    cache_key = make_cache_key(req) if cacheable else None

    if cacheable:
        cached = get_cached(cache_key)
        if cached is not None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            # Cache hit pe Groq ka kharcha nahi hua, toh tokens 0 log karte hain
            log_usage(key["id"], cached.model, 0, 0, latency_ms, cache_hit=1)
            response.headers["X-Cache"] = "HIT"
            return cached

    try:
        result = await chat_completion(req)
    except GroqError as e:
        raise HTTPException(status_code=502, detail=str(e))

    latency_ms = int((time.perf_counter() - started) * 1000)
    log_usage(
        key["id"],
        result.model,
        result.prompt_tokens,
        result.completion_tokens,
        latency_ms,
        cache_hit=0,
    )

    if cacheable:
        set_cached(cache_key, result)
        response.headers["X-Cache"] = "MISS"

    return result