from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTSCOPE_", env_file=".env", extra="ignore", case_sensitive=False
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000
    allowed_origins: list[str] = ["http://localhost:3000"]
    database_url: str = "postgresql+asyncpg://agentscope:agentscope@localhost:5432/agentscope"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    jwt_secret: str = "development-only-jwt-secret-change-me-now"  # noqa: S105
    token_hash_secret: str = "development-only-hash-secret-change-me"  # noqa: S105
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=7, ge=1, le=30)
    refresh_cookie_secure: bool = False
    refresh_cookie_name: str = "agentscope_refresh"
    ingest_max_batch_events: int = Field(default=500, ge=1, le=2000)
    ingest_max_batch_bytes: int = Field(default=2_000_000, ge=1000, le=10_000_000)
    ingest_max_event_bytes: int = Field(default=256_000, ge=1000, le=1_000_000)
    ingest_max_content_bytes: int = Field(default=64_000, ge=100, le=500_000)
    ingest_max_metadata_bytes: int = Field(default=32_000, ge=100, le=250_000)
    ingest_rate_limit_per_minute: int = Field(default=600, ge=1, le=100_000)

    @field_validator("jwt_secret", "token_hash_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("must contain at least 32 characters")
        return value

    def validate_for_startup(self) -> None:
        if self.environment == "production":
            forbidden = ("development-only", "change-me")
            if any(marker in self.jwt_secret.lower() for marker in forbidden):
                raise ValueError("AGENTSCOPE_JWT_SECRET must be changed in production")
            if any(marker in self.token_hash_secret.lower() for marker in forbidden):
                raise ValueError("AGENTSCOPE_TOKEN_HASH_SECRET must be changed in production")
            if not self.refresh_cookie_secure:
                raise ValueError("secure refresh cookies are required in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
