"""CHIRPS v3 connector: monthly, global, Final product, point extraction.

Design notes
------------
* Only the Final product is used, so a series is homogeneous.
* Two access backends share one client (``ChirpsV3Client``):
  - ``ChirpsMonthlyStore`` (this module) downloads whole monthly files into a cache, with a
    SHA-256 provenance sidecar. Archival-grade provenance, but ~22 MB per month.
  - ``ChirpsRemoteStore`` (chirps_remote.py) reads ONE pixel per month with HTTP range
    requests and caches the value. Much faster; provenance records the server-reported
    size, ETag, and Last-Modified instead of a file hash.
* Missing values are returned as ``None``. A missing value is NEVER converted to 0.
* The monthly file URL (base_url + monthly/global/tifs/chirps-v3.0.YYYY.MM.tif) was verified
  by a real run. Files are LZW strips with no nodata tag, so the documented -9999 sentinel
  is handled explicitly.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
import rasterio
from pydantic import BaseModel, ConfigDict
from rasterio.errors import RasterioIOError
from rasterio.windows import Window

from climateadapt.config import Settings
from climateadapt.data.coverage import check_month_available, check_point_in_nominal_coverage
from climateadapt.data.errors import (
    DataIntegrityError,
    DataNotAvailableError,
    DownloadError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.data.periods import YearMonth, iter_months
from climateadapt.data.provenance import Provenance

logger = logging.getLogger(__name__)

DATASET_NAME = "CHIRPS"
DATASET_VERSION = "3.0"
MONTHLY_GLOBAL_TIF_PATH = "monthly/global/tifs"
MISSING_SENTINEL = -9999.0
DEFAULT_USER_AGENT = "climateadapt-lab/0.1 (research prototype)"

# CHC stores the 0.05 degree pixel size with float32 precision, so cell edges drift by up to
# ~2e-6 degrees across the grid. Edge detection therefore needs a tolerance: 1e-3 of a cell
# is about 5e-5 degrees (roughly 5 m).
BOUNDARY_TOLERANCE_CELLS = 1e-3

CITATION = (
    "Funk, C. et al. The Climate Hazards Center Infrared Precipitation with Stations, "
    "Version 3. Scientific Data 13, 718 (2026). https://doi.org/10.1038/s41597-026-07096-4"
)
DATA_DOI = "https://doi.org/10.15780/G2JQ0P"
LICENSE_NOTE = (
    "Public domain / CC BY 4.0 as stated by the Climate Hazards Center and the Scientific "
    "Data descriptor. Cite the dataset and record the access date."
)

CHIRPS_V3_LIMITATIONS: tuple[str, ...] = (
    "CHIRPS v3 is a satellite-and-station blended gridded estimate at 0.05 degrees "
    "(roughly 5 km), land only. A point value is the value of the containing grid cell, "
    "not a gauge measurement.",
    "Published validation covers selected regions. This project has performed no "
    "validation of CHIRPS v3 at the requested location.",
    "Station density varies strongly by region and period; sparsely gauged or gap-filled "
    "areas are more uncertain (see CHC station-density and fill-map diagnostics).",
    "CHIRPS v3 applies gauge-undercatch correction and is systematically somewhat wetter "
    "than CHIRPS v2. Do not mix versions within one baseline or comparison.",
    "Only the Final product is used. Recent months may be unavailable until published.",
)

BOUNDARY_LIMITATION = (
    "The requested point lies (within about 5 m) on the edge or corner of CHIRPS grid cells. "
    "Which neighbouring cell is used is decided by floating-point rounding and is effectively "
    "arbitrary. Use a point inside a cell, or treat the neighbouring cells as equally valid."
)


def monthly_filename(month: YearMonth) -> str:
    return f"chirps-v3.0.{month.year:04d}.{month.month:02d}.tif"


def not_found_message(month: YearMonth, url: str) -> str:
    return (
        f"CHIRPS v3 Final file for {month} was not found at {url}. If the month ended "
        "recently, the Final product may not be published yet (CHC states it is typically "
        "released in the third week of the following month). Otherwise check the base URL "
        "and file naming."
    )


def _sidecar_path(tif_path: Path) -> Path:
    return tif_path.with_suffix(".provenance.json")


def _utc_today() -> date:
    return datetime.now(UTC).date()


# ---------------------------------------------------------------- point sampling


@dataclass(frozen=True)
class PointSample:
    """Result of reading one grid cell."""

    value_mm: float | None
    row: int
    col: int
    pixel_center_latitude: float
    pixel_center_longitude: float
    declared_nodata: float | None
    on_cell_boundary: bool


@dataclass(frozen=True)
class PointReading:
    """A sampled value together with the provenance of the file it came from."""

    sample: PointSample
    provenance: Provenance


def _classify_value(raw: float, declared_nodata: float | None) -> float | None:
    """Return a valid non-negative value, or None if missing. Raise on corrupt values."""
    if math.isnan(raw):
        return None
    if math.isinf(raw):
        raise DataIntegrityError("Raster contains an infinite precipitation value.")
    if declared_nodata is not None and not math.isnan(declared_nodata):
        if raw == declared_nodata:
            return None
    if raw == MISSING_SENTINEL:
        return None
    if raw < 0:
        raise DataIntegrityError(
            f"Unexpected negative precipitation value {raw} that is not a known nodata marker."
        )
    return raw


def _near_integer(value: float) -> bool:
    return abs(value - round(value)) <= BOUNDARY_TOLERANCE_CELLS


def sample_dataset(src: Any, latitude: float, longitude: float, *, name: str) -> PointSample:
    """Read the grid cell containing a point from an open raster (no interpolation)."""
    if src.crs is None or not src.crs.is_geographic:
        raise DataIntegrityError(f"{name} does not have a geographic CRS.")
    transform = src.transform
    if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
        raise DataIntegrityError(f"{name} is not a north-up, unrotated raster.")

    col_f = (longitude - transform.c) / transform.a
    row_f = (latitude - transform.f) / transform.e
    col, row = math.floor(col_f), math.floor(row_f)
    if not (0 <= col < src.width and 0 <= row < src.height):
        raise OutsideCoverageError(
            f"Point (lat={latitude}, lon={longitude}) is outside the raster extent of {name}."
        )

    raw = float(src.read(1, window=Window(col, row, 1, 1))[0, 0])
    declared = src.nodatavals[0] if src.nodatavals else None
    return PointSample(
        value_mm=_classify_value(raw, declared),
        row=row,
        col=col,
        pixel_center_latitude=transform.f + (row + 0.5) * transform.e,
        pixel_center_longitude=transform.c + (col + 0.5) * transform.a,
        declared_nodata=declared,
        on_cell_boundary=_near_integer(col_f) or _near_integer(row_f),
    )


def sample_point(path: Path, latitude: float, longitude: float) -> PointSample:
    """Read the grid cell containing a point from a local GeoTIFF."""
    with rasterio.open(path) as src:
        return sample_dataset(src, latitude, longitude, name=path.name)


# ---------------------------------------------------------------- backend protocol


class PointStore(Protocol):
    """What ``ChirpsV3Client`` needs from an access backend."""

    @property
    def cache_dir(self) -> Path: ...

    def assert_month_available(self, month: YearMonth) -> None: ...

    def read_point(self, month: YearMonth, latitude: float, longitude: float) -> PointReading: ...

    def prefetch(self, months: list[YearMonth], latitude: float, longitude: float) -> None: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------- download backend


class ChirpsMonthlyStore:
    """Download-and-cache layer for monthly global CHIRPS v3 Final GeoTIFFs."""

    def __init__(
        self,
        *,
        base_url: str,
        cache_dir: Path,
        http_client: httpx.Client | None = None,
        allow_downloads: bool = True,
        timeout_seconds: float = 60.0,
        user_agent: str = DEFAULT_USER_AGENT,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._cache_dir = Path(cache_dir)
        self._owns_client = http_client is None
        self._client = (
            http_client if http_client is not None else httpx.Client(follow_redirects=True)
        )
        self._allow_downloads = allow_downloads
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._today = today

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def url_for(self, month: YearMonth) -> str:
        return f"{self._base_url}/{MONTHLY_GLOBAL_TIF_PATH}/{monthly_filename(month)}"

    def cache_path_for(self, month: YearMonth) -> Path:
        return self._cache_dir / monthly_filename(month)

    def assert_month_available(self, month: YearMonth) -> None:
        check_month_available(month, today=self._today())

    def ensure_cached(self, month: YearMonth) -> tuple[Path, Provenance]:
        """Return the cached file and its provenance, downloading if needed."""
        self.assert_month_available(month)
        path = self.cache_path_for(month)

        cached = self._load_valid_cache(path, month)
        if cached is not None:
            return path, cached

        if not self._allow_downloads:
            raise DataNotAvailableError(
                f"CHIRPS v3 Final {month} is not in the local cache and downloads "
                "are disabled (CLIMATEADAPT_ALLOW_DOWNLOADS=false)."
            )
        return path, self._download(month, path)

    def read_point(self, month: YearMonth, latitude: float, longitude: float) -> PointReading:
        path, provenance = self.ensure_cached(month)
        return PointReading(sample=sample_point(path, latitude, longitude), provenance=provenance)

    def prefetch(self, months: list[YearMonth], latitude: float, longitude: float) -> None:
        """Warm the cache sequentially (whole-file downloads are bandwidth bound)."""
        for month in months:
            self.ensure_cached(month)

    def _load_valid_cache(self, path: Path, month: YearMonth) -> Provenance | None:
        sidecar = _sidecar_path(path)
        if not path.exists() or not sidecar.exists():
            return None
        try:
            provenance = Provenance.model_validate_json(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Unreadable provenance for %s; treating cache as invalid.", path)
            return None
        if (
            provenance.access_mode != "download"
            or provenance.size_bytes != path.stat().st_size
            or provenance.year != month.year
            or provenance.month != month.month
        ):
            logger.warning("Cache for %s does not match its provenance; discarding.", path)
            return None
        return provenance

    def _download(self, month: YearMonth, path: Path) -> Provenance:
        url = self.url_for(month)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        digest = hashlib.sha256()
        size = 0
        logger.info("Downloading %s", url)
        try:
            with self._client.stream(
                "GET",
                url,
                headers={"User-Agent": self._user_agent, "Accept-Encoding": "identity"},
                timeout=self._timeout,
            ) as response:
                if response.status_code == 404:
                    raise DataNotAvailableError(not_found_message(month, url))
                if response.status_code != 200:
                    raise DownloadError(
                        f"Unexpected HTTP status {response.status_code} for {url}."
                    )
                with open(tmp, "wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                self._check_length(response, size, url)

            self._validate_raster(tmp, url)
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
                sha256=digest.hexdigest(),
                size_bytes=size,
                cache_path=str(path),
                citation=CITATION,
                doi=DATA_DOI,
                license_note=LICENSE_NOTE,
                access_mode="download",
            )
            _sidecar_path(path).unlink(missing_ok=True)
            os.replace(tmp, path)
            _sidecar_path(path).write_text(
                provenance.model_dump_json(indent=2), encoding="utf-8"
            )
            return provenance
        except httpx.HTTPError as exc:
            raise DownloadError(f"Network failure while downloading {url}: {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _check_length(response: httpx.Response, size: int, url: str) -> None:
        encoding = response.headers.get("content-encoding", "identity").lower()
        declared = response.headers.get("content-length")
        if declared is None or encoding not in ("", "identity"):
            return
        try:
            expected = int(declared)
        except ValueError:
            return
        if expected != size:
            raise DataIntegrityError(
                f"Downloaded size {size} bytes does not match Content-Length {expected} "
                f"for {url}."
            )

    @staticmethod
    def _validate_raster(path: Path, url: str) -> None:
        try:
            with rasterio.open(path) as src:
                if src.count < 1:
                    raise DataIntegrityError(f"Raster from {url} has no bands.")
        except RasterioIOError as exc:
            raise DataIntegrityError(
                f"File downloaded from {url} is not a readable raster: {exc}"
            ) from exc


# ---------------------------------------------------------------- series and client


class MonthlyValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    month: int
    precipitation_mm: float | None
    status: Literal["ok", "missing_value"]


class PointSeries(BaseModel):
    """A monthly precipitation series for one grid cell, with full traceability."""

    model_config = ConfigDict(extra="forbid")

    dataset: str
    version: str
    product: Literal["final"]
    variable: str
    units: str
    requested_latitude: float
    requested_longitude: float
    pixel_center_latitude: float
    pixel_center_longitude: float
    point_on_cell_boundary: bool
    values: list[MonthlyValue]
    provenance: list[Provenance]
    limitations: list[str]


class ChirpsV3Client:
    """Point time-series access to CHIRPS v3 Final monthly precipitation."""

    def __init__(self, store: PointStore) -> None:
        self._store = store

    @property
    def store(self) -> PointStore:
        return self._store

    def prefetch(self, latitude: float, longitude: float, months: list[YearMonth]) -> None:
        """Warm the cache for these months (validated first; parallel for remote reads)."""
        lat, lon = check_point_in_nominal_coverage(latitude, longitude)
        for month in months:
            self._store.assert_month_available(month)
        self._store.prefetch(months, lat, lon)

    def monthly_point_series(
        self,
        latitude: float,
        longitude: float,
        start: YearMonth,
        end: YearMonth,
    ) -> PointSeries:
        """Return monthly totals (mm/month) for the grid cell containing the point.

        All validation (coordinates, coverage, month availability) runs BEFORE any
        network access so a bad request never triggers traffic.
        """
        lat, lon = check_point_in_nominal_coverage(latitude, longitude)
        months = list(iter_months(start, end))
        for month in months:
            self._store.assert_month_available(month)

        values: list[MonthlyValue] = []
        provenance: list[Provenance] = []
        first: PointSample | None = None
        on_boundary = False

        for month in months:
            reading = self._store.read_point(month, lat, lon)
            sample = reading.sample
            on_boundary = on_boundary or sample.on_cell_boundary
            if first is None:
                first = sample
            elif not self._same_cell(first, sample):
                raise DataIntegrityError(
                    f"Grid geometry of {monthly_filename(month)} differs from earlier files "
                    "in the series; refusing to combine."
                )
            values.append(
                MonthlyValue(
                    year=month.year,
                    month=month.month,
                    precipitation_mm=sample.value_mm,
                    status="ok" if sample.value_mm is not None else "missing_value",
                )
            )
            provenance.append(reading.provenance)

        if first is None:  # unreachable: iter_months yields at least one month
            raise RuntimeError("No months were processed.")

        limitations = list(CHIRPS_V3_LIMITATIONS)
        if on_boundary:
            limitations.insert(0, BOUNDARY_LIMITATION)

        return PointSeries(
            dataset=DATASET_NAME,
            version=DATASET_VERSION,
            product="final",
            variable="precipitation",
            units="mm/month",
            requested_latitude=lat,
            requested_longitude=lon,
            pixel_center_latitude=first.pixel_center_latitude,
            pixel_center_longitude=first.pixel_center_longitude,
            point_on_cell_boundary=on_boundary,
            values=values,
            provenance=provenance,
            limitations=limitations,
        )

    @staticmethod
    def _same_cell(first: PointSample, other: PointSample) -> bool:
        return (
            (other.row, other.col) == (first.row, first.col)
            and math.isclose(
                other.pixel_center_latitude, first.pixel_center_latitude, abs_tol=1e-9
            )
            and math.isclose(
                other.pixel_center_longitude, first.pixel_center_longitude, abs_tol=1e-9
            )
        )


def accumulated_total_mm(series: PointSeries) -> float:
    """Sum a series. Raises MissingDataError if any month is missing (no partial sums)."""
    if not series.values:
        raise ValueError("Series is empty.")
    present = [v.precipitation_mm for v in series.values if v.precipitation_mm is not None]
    if len(present) != len(series.values):
        missing = [
            f"{v.year:04d}-{v.month:02d}" for v in series.values if v.precipitation_mm is None
        ]
        raise MissingDataError(
            "Cannot compute an accumulated total because values are missing for: "
            + ", ".join(missing)
            + ". Partial sums would understate rainfall, so none is returned."
        )
    return math.fsum(present)


def build_chirps_client(
    settings: Settings, *, http_client: httpx.Client | None = None
) -> ChirpsV3Client:
    """Construct a client from application settings (remote reads by default)."""
    cache_root = settings.data_dir / "cache" / "chirps_v3"
    if settings.chirps_access == "remote":
        from climateadapt.data.chirps_remote import ChirpsRemoteStore

        return ChirpsV3Client(
            ChirpsRemoteStore(
                base_url=settings.chirps_base_url,
                cache_dir=cache_root / "remote_points",
                http_client=http_client,
                allow_downloads=settings.allow_downloads,
                timeout_seconds=settings.http_timeout_seconds,
                user_agent=settings.http_user_agent,
                max_workers=settings.prefetch_workers,
            )
        )
    return ChirpsV3Client(
        ChirpsMonthlyStore(
            base_url=settings.chirps_base_url,
            cache_dir=cache_root / "monthly_global",
            http_client=http_client,
            allow_downloads=settings.allow_downloads,
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.http_user_agent,
        )
    )