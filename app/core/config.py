from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://hookrelay:hookrelay@localhost:5432/hookrelay"
    redis_url: str = "redis://localhost:6379/0"
    environment: str = "development"
    allow_insecure_endpoints: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

allow_insecure_endpoints: bool = False