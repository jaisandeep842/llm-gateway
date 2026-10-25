import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, status

from app.config import settings
from app.db import get_db


def generate_api_key() -> str:
    """Naya random API key banata hai, jaise gw_xxxxx."""
    return "gw_" + secrets.token_urlsafe(32)


def hash_key(raw_key: str) -> str:
    """Key ko SHA-256 se hash karta hai. DB mein sirf hash save hota hai."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_admin(x_admin_key: str = Header(default="")) -> None:
    """Admin endpoints ke liye. ADMIN_KEY match nahi hui toh 401."""
    if not settings.admin_key or not secrets.compare_digest(x_admin_key, settings.admin_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")


def get_current_key(x_api_key: str = Header(default="")) -> dict:
    """/chat jaise endpoints ke liye. Valid active key ka record return karta hai."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name FROM api_keys WHERE key_hash = ? AND active = 1",
            (hash_key(x_api_key),),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return {"id": row["id"], "name": row["name"]}