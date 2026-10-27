"""Environment-based application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a local .env file.

    All variables use the ``CLIMATEADAPT_`` prefix. No secrets are stored here.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLIMATEADAPT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    data_dir: Path = Path("data")
    allow_downloads: bool = True
    http_timeout_seconds: float = Field(default=60.0, gt=0)
    http_user_agent: str = "climateadapt-lab/0.1 (research prototype)"
    chirps_base_url: str = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0"
    chirps_access: Literal["remote", "download"] = "remote"
    prefetch_workers: int = Field(default=4, ge=1, le=8)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings (call ``get_settings.cache_clear()`` in tests if needed)."""
    return Settings()