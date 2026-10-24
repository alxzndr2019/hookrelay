from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://hookrelay:hookrelay@localhost:5432/hookrelay"
    redis_url: str = "redis://localhost:6379/0"
    environment: str = "development"
    allow_insecure_endpoints: bool = True
    worker_concurrency: int = 50
    worker_poll_seconds: float = 1.0
    delivery_timeout_seconds: float = 10.0
    lease_seconds: int = 60
    response_body_limit: int = 2048


@lru_cache
def get_settings() -> Settings:
    return Settings()

allow_insecure_endpoints: bool = True
worker_concurrency: int = 50
worker_poll_seconds: float = 1.0
delivery_timeout_seconds: float = 10.0
lease_seconds: int = 60
response_body_limit: int = 2048