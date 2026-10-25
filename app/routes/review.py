import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.cache import get_cached, make_cache_key, set_cached
from app.db import get_db
from app.providers.groq import GroqError, chat_completion
from app.ratelimit import enforce_rate_limit
from app.schemas import ChatMessage, ChatRequest

MAX_FILES = 5
MAX_FILE_BYTES = 20 * 1024

SYSTEM_PROMPT = (
    "You are a senior code reviewer. Find real bugs only: logic errors, crashes, "
    "security issues, and unhandled edge cases. Do not comment on style. "
    "For each bug give: line number (if known), severity (high, medium or low), "
    "a one-line explanation, and a short fix. If there are no real bugs, say so."
)

router = APIRouter(tags=["review"])


class ReviewFile(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class ReviewRequest(BaseModel):
    files: list[ReviewFile] = Field(min_length=1, max_length=MAX_FILES)


class ReviewResult(BaseModel):
    name: str
    review: str | None = None
    error: str | None = None
    cache: str | None = None


class ReviewResponse(BaseModel):
    results: list[ReviewResult]


def _log_usage(key_id: int, model: str, prompt_tokens, completion_tokens, latency_ms: int, cache_hit: int) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO usage_logs
                (api_key_id, model, prompt_tokens, completion_tokens, latency_ms, cache_hit)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key_id, model, prompt_tokens, completion_tokens, latency_ms, cache_hit),
        )


async def review_one(file: ReviewFile, key_id: int) -> ReviewResult:
    if len(file.content.encode("utf-8")) > MAX_FILE_BYTES:
        return ReviewResult(name=file.name, error="File too large (max 20 KB)")

    req = ChatRequest(
        messages=[
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=f"File: {file.name}\n\n```\n{file.content}\n```"),
        ],
        max_tokens=1024,
        temperature=0,
    )

    started = time.perf_counter()
    cache_key = make_cache_key(req)

    cached = get_cached(cache_key)
    if cached is not None:
        latency = int((time.perf_counter() - started) * 1000)
        _log_usage(key_id, cached.model, 0, 0, latency, cache_hit=1)
        return ReviewResult(name=file.name, review=cached.content, cache="HIT")

    try:
        result = await chat_completion(req)
    except GroqError as e:
        return ReviewResult(name=file.name, error=str(e))

    latency = int((time.perf_counter() - started) * 1000)
    _log_usage(key_id, result.model, result.prompt_tokens, result.completion_tokens, latency, cache_hit=0)
    set_cached(cache_key, result)
    return ReviewResult(name=file.name, review=result.content, cache="MISS")


@router.post("/review", response_model=ReviewResponse)
async def review(body: ReviewRequest, key: dict = Depends(enforce_rate_limit)):
    # Files ek-ek karke review hongi, taaki Groq ki rate limit pe load kam rahe
    results = []
    for f in body.files:
        results.append(await review_one(f, key["id"]))
    return ReviewResponse(results=results)