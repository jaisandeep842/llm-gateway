import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.schemas import ChatRequest, ChatResponse


class GroqError(Exception):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.groq_api_key}"}


def _payload(req: ChatRequest, stream: bool) -> dict:
    payload = {
        "model": settings.groq_model,
        "messages": [m.model_dump() for m in req.messages],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    return payload


async def chat_completion(req: ChatRequest) -> ChatResponse:
    if not settings.groq_api_key:
        raise GroqError("GROQ_API_KEY is not set in .env")

    url = f"{settings.groq_base_url}/chat/completions"
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        resp = await client.post(url, json=_payload(req, stream=False), headers=_headers())

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


async def stream_completion(req: ChatRequest) -> AsyncIterator[dict]:
    """Groq se tokens ek-ek karke yield karta hai.
    Yield hote hain: {"delta": "..."} for each piece, aur last mein {"done": True, ...}."""
    if not settings.groq_api_key:
        raise GroqError("GROQ_API_KEY is not set in .env")

    url = f"{settings.groq_base_url}/chat/completions"
    model = settings.groq_model
    usage: dict = {}

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        async with client.stream(
            "POST", url, json=_payload(req, stream=True), headers=_headers()
        ) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", errors="replace")
                raise GroqError(f"Groq API error {resp.status_code}: {body}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    break

                chunk = json.loads(data)
                model = chunk.get("model", model)
                if chunk.get("usage"):
                    usage = chunk["usage"]

                for choice in chunk.get("choices", []):
                    text = (choice.get("delta") or {}).get("content")
                    if text:
                        yield {"delta": text}

    yield {"done": True, "model": model, "usage": usage}