import json
import time

import numpy as np
from fastembed import TextEmbedding

from app.config import settings
from app.db import get_db
from app.schemas import ChatRequest, ChatResponse

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    """Model ek hi baar load hota hai, phir memory mein rehta hai."""
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=settings.embedding_model)
    return _model


def _last_user_message(req: ChatRequest) -> str:
    """Embedding user ke last message ka banega, poori conversation ka nahi."""
    for m in reversed(req.messages):
        if m.role == "user":
            return m.content
    return req.messages[-1].content


def embed(text: str) -> np.ndarray:
    vec = next(iter(_get_model().embed([text])))
    # Normalize: taaki dot product hi cosine similarity ban jaaye
    return vec / np.linalg.norm(vec)


def find_similar(req: ChatRequest) -> ChatResponse | None:
    """Same model ke saare cached entries mein se best match dhoondhta hai."""
    query_text = _last_user_message(req)
    query_vec = embed(query_text)

    with get_db() as conn:
        rows = conn.execute(
            "SELECT embedding, response_json FROM semantic_cache WHERE model = ?",
            (settings.groq_model,),
        ).fetchall()

    best_score = -1.0
    best_response = None
    for row in rows:
        stored = np.frombuffer(row["embedding"], dtype=np.float32)
        score = float(np.dot(query_vec, stored))
        if score > best_score:
            best_score = score
            best_response = row["response_json"]

    if best_response is not None and best_score >= settings.semantic_threshold:
        return ChatResponse.model_validate_json(best_response)
    return None


def store(req: ChatRequest, resp: ChatResponse) -> None:
    """Naya answer embedding ke saath save karta hai."""
    vec = embed(_last_user_message(req)).astype(np.float32)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO semantic_cache (model, prompt, embedding, response_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                settings.groq_model,
                _last_user_message(req),
                vec.tobytes(),
                resp.model_dump_json(),
            ),
        )