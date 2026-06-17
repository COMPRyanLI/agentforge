"""Application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Postgres (async driver)
    database_url: str = "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge"
    # Redis (queue + pub/sub + cache)
    redis_url: str = "redis://localhost:6379/0"
    # Local Gemma via Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"

    app_name: str = "AgentForge"

    # CORS — origins allowed to call the API from a browser (e.g. the Vite dev server)
    cors_origins: list[str] = ["http://localhost:5173"]

    # JWT — SECRET_KEY has no default so pydantic raises at startup if unset
    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 h


@lru_cache
def get_settings() -> Settings:
    return Settings()
