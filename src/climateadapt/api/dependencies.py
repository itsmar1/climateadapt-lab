"""FastAPI dependencies. Tests replace these via ``app.dependency_overrides``."""

from __future__ import annotations

import logging
from functools import lru_cache

from climateadapt.api.jobs import JobStore
from climateadapt.config import get_settings
from climateadapt.data.chirps import ChirpsV3Client, build_chirps_client
from climateadapt.data.era5_land import Era5LandClient, build_era5_land_client

logger = logging.getLogger(__name__)


@lru_cache
def get_chirps_client() -> ChirpsV3Client:
    """One shared CHIRPS client (and HTTP connection pool) per process."""
    return build_chirps_client(get_settings())


@lru_cache
def get_era5_client() -> Era5LandClient:
    """One shared ERA5-Land client (and local cache) per process."""
    return build_era5_land_client(get_settings())


@lru_cache
def get_job_store() -> JobStore:
    """One shared background-job store per process (see ``api/jobs.py``)."""
    settings = get_settings()
    return JobStore(
        max_workers=settings.api_job_max_workers,
        timeout_seconds=settings.api_job_timeout_seconds,
        ttl_seconds=settings.api_job_ttl_seconds,
        max_jobs=settings.api_job_max_jobs,
    )


def close_shared_clients() -> None:
    """Release shared resources at shutdown. Best-effort; never raises."""
    try:
        get_job_store().shutdown()
    except Exception:
        logger.exception("Error shutting down the job store.")
    try:
        # Only the real cached client is closed (dependency_overrides do not apply here,
        # so test doubles are never touched). ERA5-Land holds no closeable handle: its
        # downloader sessions are short-lived and garbage-collected.
        if get_chirps_client.cache_info().currsize:
            get_chirps_client().store.close()
    except Exception:
        logger.exception("Error closing the shared CHIRPS client.")
    finally:
        get_chirps_client.cache_clear()
        get_era5_client.cache_clear()
        get_job_store.cache_clear()
