"""Application settings, loaded from environment / .env."""

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


settings = Settings()
