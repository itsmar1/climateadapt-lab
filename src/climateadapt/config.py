"""Environment-based application configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a local .env file.

    All variables use the ``CLIMATEADAPT_`` prefix. No secrets are required yet.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLIMATEADAPT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings (call ``get_settings.cache_clear()`` in tests if needed)."""
    return Settings()