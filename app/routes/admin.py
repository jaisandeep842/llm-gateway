from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.db import get_db
from app.security import generate_api_key, hash_key, verify_admin

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_admin)],
)


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class KeyCreated(BaseModel):
    id: int
    name: str
    api_key: str  # sirf is response mein dikhega, phir kabhi nahi


@router.post("/keys", response_model=KeyCreated, status_code=201)
def create_key(body: KeyCreate):
    raw_key = generate_api_key()
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO api_keys (name, key_hash) VALUES (?, ?)",
            (body.name, hash_key(raw_key)),
        )
        key_id = cur.lastrowid
    return KeyCreated(id=key_id, name=body.name, api_key=raw_key)