from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0, le=2)
    stream: bool = False


class ChatResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None