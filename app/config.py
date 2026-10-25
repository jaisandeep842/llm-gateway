from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    redis_url: str = "redis://localhost:6379"
    request_timeout: float = 30.0
    admin_key: str = ""
    database_path: str = "gateway.db"
    rate_limit_per_minute: int = 10
    cache_ttl_seconds: int = 3600
    semantic_cache_enabled: bool = False
    semantic_threshold: float = 0.95
    embedding_model: str = "BAAI/bge-small-en-v1.5"


settings = Settings()