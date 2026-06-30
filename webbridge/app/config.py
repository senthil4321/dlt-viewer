from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "dlt-webbridge"
    app_version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8008
    log_level: str = "info"
    heartbeat_interval_sec: float = Field(default=5.0, gt=0.0)
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )

    model_config = SettingsConfigDict(
        env_prefix="WEBBRIDGE_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
