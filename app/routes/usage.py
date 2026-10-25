from fastapi import APIRouter, Depends

from app.db import get_db
from app.security import get_current_key

router = APIRouter(tags=["usage"])


@router.get("/usage")
def my_usage(key: dict = Depends(get_current_key)):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS requests,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
            FROM usage_logs
            WHERE api_key_id = ?
            """,
            (key["id"],),
        ).fetchone()

    return {
        "key_name": key["name"],
        "requests": row["requests"],
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "total_tokens": row["prompt_tokens"] + row["completion_tokens"],
        "avg_latency_ms": round(row["avg_latency_ms"], 1),
    }