"""Runtime settings, read from environment variables prefixed ``CLP_`` (or a .env file)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "development-only-secret-change-me-0000000000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLP_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    # PostgreSQL (+ PostGIS) on servers; SQLite is the offline / desktop store.
    database_url: str = "sqlite:///./civillabpro.db"
    jwt_secret: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    allow_self_registration: bool = True
    allow_self_approval: bool = False  # four-eyes rule: a design is approved by someone other than its designer
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def _production_is_configured(self) -> Settings:
        if self.env == "production":
            if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("CLP_JWT_SECRET must be set to a random value of at least 32 characters in production.")
            if self.database_url.startswith("sqlite") and "CLP_ALLOW_SQLITE" not in __import__("os").environ:
                raise ValueError("Production expects PostgreSQL. Set CLP_DATABASE_URL, or CLP_ALLOW_SQLITE=1 for a single-user desktop install.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
