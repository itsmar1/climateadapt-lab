"""CHIRPS v3 remote single-pixel reads (HTTP range requests through GDAL /vsicurl/).

Why: a whole monthly file is ~22 MB (and ~35 s on the verified connection), while one pixel
needs only a few kilobytes. A real probe showed a remote read matching the downloaded value
exactly (open ~3.8 s, read ~0.3 s).

Behaviour
---------
* Each (point, month) result is cached as a small JSON record with provenance. Remote files
  are identified by the server-reported Content-Length, ETag, and Last-Modified (from a HEAD
  request, best effort). No SHA-256 exists because the whole file is never downloaded; use
  ``CLIMATEADAPT_CHIRPS_ACCESS=download`` when archival-grade file hashes are required.
* HEAD returning 404 means the file is not published (a clear ``DataNotAvailableError``).
  Any other non-200 HEAD answer only means metadata is unavailable; the read is still tried.
* Points are rounded to 4 decimals (about 11 m) so cache keys are stable. This is below the
  cell-boundary tolerance, so it can only matter for points already flagged as on an edge.
* ``prefetch`` reads missing months in parallel (a small, configurable thread pool).
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import rasterio
from pydantic import BaseModel, ConfigDict
from rasterio.errors import RasterioIOError

from climateadapt.data.chirps import (
    CITATION,
    DATA_DOI,
    DATASET_NAME,
    DATASET_VERSION,
    DEFAULT_USER_AGENT,
    LICENSE_NOTE,
    MONTHLY_GLOBAL_TIF_PATH,
    PointReading,
    PointSample,
    monthly_filename,
    not_found_message,
    sample_dataset,
)
from climateadapt.data.coverage import check_month_available
from climateadapt.data.errors import DataNotAvailableError, DownloadError
from climateadapt.data.periods import YearMonth
from climateadapt.data.provenance import Provenance

logger = logging.getLogger(__name__)

RasterOpener = Callable[[str], AbstractContextManager[Any]]


def vsicurl_opener(*, user_agent: str, timeout_seconds: float) -> RasterOpener:
    """Open a remote GeoTIFF through GDAL's /vsicurl/ virtual file system."""
    options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_USERAGENT": user_agent,
        "GDAL_HTTP_TIMEOUT": str(max(1, int(timeout_seconds))),
        "GDAL_HTTP_MAX_RETRY": "3",
        "GDAL_HTTP_RETRY_DELAY": "2",
    }

    @contextmanager
    def _open(url: str) -> Iterator[Any]:
        with rasterio.Env(**options), rasterio.open("/vsicurl/" + url) as src:
            yield src

    return _open


class RemotePointRecord(BaseModel):
    """One cached point-month read."""

    model_config = ConfigDict(extra="forbid")

    requested_latitude: float
    requested_longitude: float
    value_mm: float | None
    row: int
    col: int
    pixel_center_latitude: float
    pixel_center_longitude: float
    declared_nodata: float | None
    on_cell_boundary: bool
    provenance: Provenance


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class ChirpsRemoteStore:
    """Remote single-pixel access with a per-point JSON cache."""

    def __init__(
        self,
        *,
        base_url: str,
        cache_dir: Path,
        http_client: httpx.Client | None = None,
        opener: RasterOpener | None = None,
        allow_downloads: bool = True,
        timeout_seconds: float = 60.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_workers: int = 4,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._cache_dir = Path(cache_dir)
        self._owns_client = http_client is None
        self._client = (
            http_client if http_client is not None else httpx.Client(follow_redirects=True)
        )
        self._opener = (
            opener
            if opener is not None
            else vsicurl_opener(user_agent=user_agent, timeout_seconds=timeout_seconds)
        )
        self._allow_downloads = allow_downloads
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._max_workers = max(1, max_workers)
        self._today = today

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def url_for(self, month: YearMonth) -> str:
        return f"{self._base_url}/{MONTHLY_GLOBAL_TIF_PATH}/{monthly_filename(month)}"

    def assert_month_available(self, month: YearMonth) -> None:
        check_month_available(month, today=self._today())

    # -------------------------------------------------------------- cache

    def _record_path(self, month: YearMonth, lat_key: float, lon_key: float) -> Path:
        return self._cache_dir / f"lat{lat_key:.4f}_lon{lon_key:.4f}" / f"{month}.json"

    def _load(
        self, path: Path, month: YearMonth, lat_key: float, lon_key: float
    ) -> PointReading | None:
        if not path.exists():
            return None
        try:
            record = RemotePointRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Unreadable cached record %s; ignoring it.", path)
            return None
        prov = record.provenance
        if (
            prov.access_mode != "remote_range_read"
            or (prov.year, prov.month) != (month.year, month.month)
            or not math.isclose(record.requested_latitude, lat_key, abs_tol=1e-9)
            or not math.isclose(record.requested_longitude, lon_key, abs_tol=1e-9)
        ):
            logger.warning("Cached record %s does not match its request; ignoring it.", path)
            return None
        sample = PointSample(
            value_mm=record.value_mm,
            row=record.row,
            col=record.col,
            pixel_center_latitude=record.pixel_center_latitude,
            pixel_center_longitude=record.pixel_center_longitude,
            declared_nodata=record.declared_nodata,
            on_cell_boundary=record.on_cell_boundary,
        )
        return PointReading(sample=sample, provenance=prov)

    # -------------------------------------------------------------- reading

    def read_point(self, month: YearMonth, latitude: float, longitude: float) -> PointReading:
        self.assert_month_available(month)
        lat_key, lon_key = round(latitude, 4), round(longitude, 4)
        path = self._record_path(month, lat_key, lon_key)

        cached = self._load(path, month, lat_key, lon_key)
        if cached is not None:
            return cached

        if not self._allow_downloads:
            raise DataNotAvailableError(
                f"CHIRPS v3 Final {month} is not in the local cache and downloads are "
                "disabled (CLIMATEADAPT_ALLOW_DOWNLOADS=false)."
            )
        return self._fetch(month, lat_key, lon_key, path)

    def _fetch(
        self, month: YearMonth, lat_key: float, lon_key: float, path: Path
    ) -> PointReading:
        url = self.url_for(month)
        etag, last_modified, size = self._head(url, month)
        logger.info("Remote read %s", url)
        try:
            with self._opener(url) as src:
                sample = sample_dataset(src, lat_key, lon_key, name=monthly_filename(month))
        except RasterioIOError as exc:
            raise DownloadError(f"Remote read of {url} failed: {exc}") from exc

        provenance = Provenance(
            dataset=DATASET_NAME,
            version=DATASET_VERSION,
            product="final",
            variable="precipitation",
            units="mm/month",
            temporal_resolution="monthly",
            year=month.year,
            month=month.month,
            source_url=url,
            retrieved_at_utc=datetime.now(UTC),
            sha256=None,
            size_bytes=size,
            cache_path=None,
            citation=CITATION,
            doi=DATA_DOI,
            license_note=LICENSE_NOTE,
            access_mode="remote_range_read",
            remote_etag=etag,
            remote_last_modified=last_modified,
        )
        record = RemotePointRecord(
            requested_latitude=lat_key,
            requested_longitude=lon_key,
            value_mm=sample.value_mm,
            row=sample.row,
            col=sample.col,
            pixel_center_latitude=sample.pixel_center_latitude,
            pixel_center_longitude=sample.pixel_center_longitude,
            declared_nodata=sample.declared_nodata,
            on_cell_boundary=sample.on_cell_boundary,
            provenance=provenance,
        )
        _atomic_write_text(path, record.model_dump_json(indent=2))
        return PointReading(sample=sample, provenance=provenance)

    def _head(self, url: str, month: YearMonth) -> tuple[str | None, str | None, int | None]:
        try:
            response = self._client.head(
                url, headers={"User-Agent": self._user_agent}, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise DownloadError(f"Network failure while checking {url}: {exc}") from exc
        if response.status_code == 404:
            raise DataNotAvailableError(not_found_message(month, url))
        if response.status_code != 200:
            logger.warning(
                "HEAD %s returned %s; provenance metadata unavailable.", url, response.status_code
            )
            return None, None, None
        length = response.headers.get("content-length")
        size = int(length) if length is not None and length.isdigit() else None
        return response.headers.get("etag"), response.headers.get("last-modified"), size

    # -------------------------------------------------------------- prefetch

    def prefetch(self, months: list[YearMonth], latitude: float, longitude: float) -> None:
        """Read all missing months (in parallel), so later reads are served from cache."""
        for month in months:
            self.assert_month_available(month)
        lat_key, lon_key = round(latitude, 4), round(longitude, 4)
        todo = [
            month
            for month in months
            if self._load(self._record_path(month, lat_key, lon_key), month, lat_key, lon_key)
            is None
        ]
        if not todo:
            return
        if not self._allow_downloads:
            raise DataNotAvailableError(
                f"{len(todo)} CHIRPS month(s) are not in the local cache and downloads are "
                "disabled (CLIMATEADAPT_ALLOW_DOWNLOADS=false)."
            )

        workers = min(self._max_workers, len(todo))
        if workers == 1:
            for month in todo:
                self.read_point(month, latitude, longitude)
            return

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(self.read_point, month, latitude, longitude) for month in todo]
            try:
                for future in futures:
                    future.result()
            except BaseException:
                for future in futures:
                    future.cancel()
                raise