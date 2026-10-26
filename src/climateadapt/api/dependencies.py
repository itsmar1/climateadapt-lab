"""FastAPI dependencies. Tests replace these via ``app.dependency_overrides``."""

from __future__ import annotations

from functools import lru_cache

from climateadapt.config import get_settings
from climateadapt.data.chirps import ChirpsV3Client, build_chirps_client


@lru_cache
def get_chirps_client() -> ChirpsV3Client:
    """One shared CHIRPS client (and HTTP connection pool) per process."""
    return build_chirps_client(get_settings())