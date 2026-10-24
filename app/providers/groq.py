import httpx

from app.config import settings
from app.schemas import ChatRequest, ChatResponse


class GroqError(Exception):
    pass


async def chat_completion(req: ChatRequest) -> ChatResponse:
    if not settings.groq_api_key:
      raise GroqError("GROQ_API_KEY is not set in .env")

    payload = {
        "model": settings.groq_model,
        "messages": [m.model_dump() for m in req.messages],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    url = f"{settings.groq_base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code != 200:
        raise GroqError(f"Groq API error {resp.status_code}: {resp.text}")

    data = resp.json()
    usage = data.get("usage", {})
    return ChatResponse(
        content=data["choices"][0]["message"]["content"],
        model=data.get("model", settings.groq_model),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )