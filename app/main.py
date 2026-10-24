from fastapi import FastAPI, HTTPException

from app.providers.groq import GroqError, chat_completion
from app.schemas import ChatRequest, ChatResponse

app = FastAPI(title="LLM Gateway")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        return await chat_completion(req)
    except GroqError as e:
        raise HTTPException(status_code=502, detail=str(e))