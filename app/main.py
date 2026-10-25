import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.cache import get_cached, is_cacheable, make_cache_key, set_cached
from app.config import settings
from app.db import get_db, init_db
from app.providers.groq import GroqError, chat_completion, stream_completion
from app.ratelimit import enforce_rate_limit
from app.routes.admin import router as admin_router
from app.routes.usage import router as usage_router
from app.schemas import ChatRequest, ChatResponse
from app.routes.review import router as review_router
from fastapi.middleware.cors import CORSMiddleware

if settings.semantic_cache_enabled:
    from app import semantic


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LLM Gateway", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
      allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin_router)
app.include_router(usage_router)
app.include_router(review_router)


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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


def sse(data: dict) -> str:
    """Ek Server-Sent Event line banata hai."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def replay_cached(resp: ChatResponse, x_cache: str) -> AsyncIterator[str]:
    """Cache hit: poora answer ek event mein bhejte hain."""
    yield sse({"delta": resp.content})
    yield sse({"done": True, "model": resp.model, "x_cache": x_cache})
    yield "data: [DONE]\n\n"


async def live_stream(
    req: ChatRequest,
    key_id: int,
    cache_key: str | None,
    cacheable: bool,
    started: float,
) -> AsyncIterator[str]:
    """Cache miss: Groq se tokens forward karte hain, stream khatam hone par cache aur usage save karte hain."""
    parts: list[str] = []
    model = settings.groq_model
    prompt_tokens = None
    completion_tokens = None

    try:
        async for ev in stream_completion(req):
            if "delta" in ev:
                parts.append(ev["delta"])
                yield sse({"delta": ev["delta"]})
            elif ev.get("done"):
                model = ev["model"]
                usage = ev.get("usage") or {}
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
    except GroqError as e:
        yield sse({"error": str(e)})
        yield "data: [DONE]\n\n"
        return

    result = ChatResponse(
        content="".join(parts),
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    log_usage(key_id, model, prompt_tokens, completion_tokens, elapsed_ms(started), cache_hit=0)

    if cacheable and cache_key is not None:
        set_cached(cache_key, result)
        if settings.semantic_cache_enabled:
            semantic.store(req, result)

    yield sse({"done": True, "model": model, "x_cache": "MISS"})
    yield "data: [DONE]\n\n"


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

    # Cache lookup (stream aur non-stream dono ke liye same)
    cached: ChatResponse | None = None
    x_cache = ""
    if cacheable:
        cached = get_cached(cache_key)
        if cached is not None:
            x_cache = "HIT"
        elif settings.semantic_cache_enabled:
            cached = semantic.find_similar(req)
            if cached is not None:
                x_cache = "HIT-SEMANTIC"

    if cached is not None:
        log_usage(key["id"], cached.model, 0, 0, elapsed_ms(started), cache_hit=1)
        if req.stream:
            return StreamingResponse(
                replay_cached(cached, x_cache),
                media_type="text/event-stream",
                headers={"X-Cache": x_cache},
            )
        response.headers["X-Cache"] = x_cache
        return cached

    # Cache miss + stream
    if req.stream:
        return StreamingResponse(
            live_stream(req, key["id"], cache_key, cacheable, started),
            media_type="text/event-stream",
            headers={"X-Cache": "MISS"},
        )

    # Cache miss + normal JSON response
    try:
        result = await chat_completion(req)
    except GroqError as e:
        raise HTTPException(status_code=502, detail=str(e))

    log_usage(
        key["id"],
        result.model,
        result.prompt_tokens,
        result.completion_tokens,
        elapsed_ms(started),
        cache_hit=0,
    )

    if cacheable and cache_key is not None:
        set_cached(cache_key, result)
        if settings.semantic_cache_enabled:
            semantic.store(req, result)
        response.headers["X-Cache"] = "MISS"

    return result