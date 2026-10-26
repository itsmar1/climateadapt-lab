"""CHIRPS v3 connector: monthly, global, Final product, point extraction.

Design notes
------------
* Only the Final product is used. Prelim is not mixed in, so a series is homogeneous.
* Files are cached on disk with a provenance sidecar (``<file>.provenance.json``).
  A cached file is trusted only if its sidecar parses and the size matches; otherwise
  it is re-downloaded (or, when downloads are disabled, reported as unavailable).
* Downloads are sequential, written to a ``.part`` file, validated as a readable
  raster, and then atomically moved into place. Single-process use is assumed.
* Missing values are returned as ``None``. A missing value is NEVER converted to 0.
* The monthly file URL (base_url + monthly/global/tifs/chirps-v3.0.YYYY.MM.tif) follows
  CHC's documented FTP layout; verify it with ``scripts/chirps_cli.py probe``.
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
from typing import Literal

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


def monthly_filename(month: YearMonth) -> str:
    return f"chirps-v3.0.{month.year:04d}.{month.month:02d}.tif"


def _sidecar_path(tif_path: Path) -> Path:
    return tif_path.with_suffix(".provenance.json")


def _utc_today() -> date:
    return datetime.now(UTC).date()


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
        self._client = http_client if http_client is not None else httpx.Client(
            follow_redirects=True
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
                f"CHIRPS v3 Final {month} is not in the local cache ({path}) and downloads "
                "are disabled (CLIMATEADAPT_ALLOW_DOWNLOADS=false)."
            )
        return path, self._download(month, path)

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
            provenance.size_bytes != path.stat().st_size
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
                    raise DataNotAvailableError(
                        f"CHIRPS v3 Final file for {month} was not found at {url}. If the "
                        "month ended recently, the Final product may not be published yet "
                        "(CHC states it is typically released in the third week of the "
                        "following month). Otherwise check the base URL and file naming."
                    )
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


@dataclass(frozen=True)
class PointSample:
    """Result of reading one grid cell."""

    value_mm: float | None
    row: int
    col: int
    pixel_center_latitude: float
    pixel_center_longitude: float
    declared_nodata: float | None


def _classify_value(raw: float, declared_nodata: float | None) -> float | None:
    """Return a valid non-negative value, or None if missing. Raise on corrupt values."""
    if math.isnan(raw):
        return None
    if math.isinf(raw):
        raise DataIntegrityError("Raster contains an infinite precipitation value.")
    if declared_nodata is not None and not math.isnan(declared_nodata) and raw == declared_nodata:
        return None
    if raw == MISSING_SENTINEL:
        return None
    if raw < 0:
        raise DataIntegrityError(
            f"Unexpected negative precipitation value {raw} that is not a known nodata marker."
        )
    return raw


def sample_point(path: Path, latitude: float, longitude: float) -> PointSample:
    """Read the grid cell containing a point (no interpolation)."""
    with rasterio.open(path) as src:
        if src.crs is None or not src.crs.is_geographic:
            raise DataIntegrityError(f"{path.name} does not have a geographic CRS.")
        transform = src.transform
        if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
            raise DataIntegrityError(f"{path.name} is not a north-up, unrotated raster.")

        col_f, row_f = (~transform) * (longitude, latitude)
        col, row = math.floor(col_f), math.floor(row_f)
        if not (0 <= col < src.width and 0 <= row < src.height):
            raise OutsideCoverageError(
                f"Point (lat={latitude}, lon={longitude}) is outside the raster extent of "
                f"{path.name}."
            )

        raw = float(src.read(1, window=Window(col, row, 1, 1))[0, 0])
        center_lon, center_lat = transform * (col + 0.5, row + 0.5)
        declared = src.nodatavals[0] if src.nodatavals else None

    return PointSample(
        value_mm=_classify_value(raw, declared),
        row=row,
        col=col,
        pixel_center_latitude=center_lat,
        pixel_center_longitude=center_lon,
        declared_nodata=declared,
    )


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
    values: list[MonthlyValue]
    provenance: list[Provenance]
    limitations: list[str]


class ChirpsV3Client:
    """Point time-series access to CHIRPS v3 Final monthly precipitation."""

    def __init__(self, store: ChirpsMonthlyStore) -> None:
        self._store = store

    @property
    def store(self) -> ChirpsMonthlyStore:
        return self._store

    def monthly_point_series(
        self,
        latitude: float,
        longitude: float,
        start: YearMonth,
        end: YearMonth,
    ) -> PointSeries:
        """Return monthly totals (mm/month) for the grid cell containing the point.

        All validation (coordinates, coverage, month availability) runs BEFORE any
        download so a bad request never triggers network traffic.
        """
        lat, lon = check_point_in_nominal_coverage(latitude, longitude)
        months = list(iter_months(start, end))
        for month in months:
            self._store.assert_month_available(month)

        values: list[MonthlyValue] = []
        provenance: list[Provenance] = []
        first: PointSample | None = None

        for month in months:
            path, prov = self._store.ensure_cached(month)
            sample = sample_point(path, lat, lon)
            if first is None:
                first = sample
            elif (
                (sample.row, sample.col) != (first.row, first.col)
                or not math.isclose(
                    sample.pixel_center_latitude, first.pixel_center_latitude, abs_tol=1e-9
                )
                or not math.isclose(
                    sample.pixel_center_longitude, first.pixel_center_longitude, abs_tol=1e-9
                )
            ):
                raise DataIntegrityError(
                    f"Grid geometry of {path.name} differs from earlier files in the series; "
                    "refusing to combine."
                )
            values.append(
                MonthlyValue(
                    year=month.year,
                    month=month.month,
                    precipitation_mm=sample.value_mm,
                    status="ok" if sample.value_mm is not None else "missing_value",
                )
            )
            provenance.append(prov)

        if first is None:  # unreachable: iter_months yields at least one month
            raise RuntimeError("No months were processed.")

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
            values=values,
            provenance=provenance,
            limitations=list(CHIRPS_V3_LIMITATIONS),
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
    """Construct a client from application settings."""
    store = ChirpsMonthlyStore(
        base_url=settings.chirps_base_url,
        cache_dir=settings.data_dir / "cache" / "chirps_v3" / "monthly_global",
        http_client=http_client,
        allow_downloads=settings.allow_downloads,
        timeout_seconds=settings.http_timeout_seconds,
        user_agent=settings.http_user_agent,
    )
    return ChirpsV3Client(store)