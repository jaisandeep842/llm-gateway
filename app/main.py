import time
from app.routes.usage import router as usage_router
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from app.db import get_db, init_db
from app.providers.groq import GroqError, chat_completion
from app.routes.admin import router as admin_router
from app.schemas import ChatRequest, ChatResponse
from app.security import get_current_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LLM Gateway", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(usage_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, key: dict = Depends(get_current_key)):
    started = time.perf_counter()
    try:
        result = await chat_completion(req)
    except GroqError as e:
        raise HTTPException(status_code=502, detail=str(e))

    latency_ms = int((time.perf_counter() - started) * 1000)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO usage_logs
                (api_key_id, model, prompt_tokens, completion_tokens, latency_ms)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key["id"], result.model, result.prompt_tokens, result.completion_tokens, latency_ms),
        )

    return result