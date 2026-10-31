"""FastAPI dependencies. Tests replace these via ``app.dependency_overrides``."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from climateadapt.agent.schemas import AgentDeps
from climateadapt.api.jobs import JobStore
from climateadapt.api.store import SqliteScenarioStore
from climateadapt.config import get_settings
from climateadapt.data.chirps import ChirpsV3Client, build_chirps_client
from climateadapt.data.era5_land import Era5LandClient, build_era5_land_client
from climateadapt.llm.provider import (
    BasetenProvider,
    LLMAuthError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)

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


class UnavailableProvider:
    """Stand-in provider when no Baseten key is configured.

    Every call raises ``LLMAuthError``, so agent runs degrade honestly to the
    labelled deterministic fallback instead of failing or inventing text.
    """

    label = "unavailable"

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMAuthError("No Baseten API key configured; LLM drafting disabled.")

    def close(self) -> None:
        return None


@lru_cache
def get_scenario_store() -> SqliteScenarioStore:
    """One shared scenario database per process (see ``api/store.py``)."""
    settings = get_settings()
    path = settings.api_db_path or (settings.data_dir / "scenarios.sqlite3")
    return SqliteScenarioStore(Path(path))


@lru_cache
def get_agent_deps() -> AgentDeps:
    """Shared agent data: clients, corpus, manifest, pages, catalog.

    A missing ingested corpus is not fatal: retrieval then yields no passages
    and the run proceeds evidenceless (recorded as a warning).
    """
    from climateadapt.rag.ingest import load_chunks, load_pages, processed_doc_ids
    from climateadapt.rag.manifest import load_manifest
    from climateadapt.recommend.loader import load_catalog

    settings = get_settings()
    processed_dir = settings.data_dir / "corpus" / "processed"
    chunks = load_chunks(processed_dir) if processed_dir.exists() else []
    pages_by_doc = (
        {doc_id: load_pages(processed_dir, doc_id) for doc_id in processed_doc_ids(processed_dir)}
        if processed_dir.exists()
        else {}
    )
    return AgentDeps(
        chirps=get_chirps_client(),
        era5=get_era5_client(),
        chunks=chunks,
        manifest=load_manifest(Path("corpus/manifest.json")),
        pages_by_doc=pages_by_doc,
        catalog=load_catalog(),
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Live Baseten provider, or the honest unavailable stand-in without a key."""
    secret = get_settings().baseten_api_key
    if secret is None or not secret.get_secret_value():
        logger.warning("No Baseten API key: scenario drafts will use the fallback.")
        return UnavailableProvider()
    return BasetenProvider()


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
    try:
        if get_scenario_store.cache_info().currsize:
            get_scenario_store().close()
    except Exception:
        logger.exception("Error closing the scenario database.")
    try:
        if get_llm_provider.cache_info().currsize:
            get_llm_provider().close()
    except Exception:
        logger.exception("Error closing the LLM provider.")
    finally:
        get_chirps_client.cache_clear()
        get_era5_client.cache_clear()
        get_job_store.cache_clear()
        get_scenario_store.cache_clear()
        get_agent_deps.cache_clear()
        get_llm_provider.cache_clear()
