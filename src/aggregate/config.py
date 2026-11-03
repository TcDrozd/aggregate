"""Settings, read from AGGREGATE_* environment variables (and .env in development)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGGREGATE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/aggregate.db"
