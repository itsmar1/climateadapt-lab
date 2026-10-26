"""ERA5-Land monthly means (Copernicus CDS): point extraction with cache and provenance.

Design notes
------------
* Dataset: ``reanalysis-era5-land-monthly-means``, product ``monthly_averaged_reanalysis``
  ("monthly means of daily means"), regular 0.1 degree grid, 1950 onwards.
* One variable per request, with a tiny area box around the point, so downloads are small.
  Missing months are grouped by identical month-sets, so requests never ask for months that
  were not needed (and never for unpublished months).
* Per-month point records (JSON, with full provenance) are cached; the raw NetCDF is kept
  too. A cached record is reused only if it parses and matches the request.
* Unit handling is explicit and tested: temperature K -> degC; total precipitation is a
  monthly mean of DAILY accumulations (m/day) and is converted to mm/month using the number
  of days in the month. File units are verified before any conversion.
* The CDS client is behind a small protocol, so everything except the real network call is
  tested offline. Credentials are read by cdsapi from ~/.cdsapirc; this module never sees
  or stores them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import xarray as xr
from pydantic import BaseModel, ConfigDict

from climateadapt.config import Settings
from climateadapt.data.coverage import (
    ERA5_LAND_FIRST_MONTH,
    ERA5_LAND_NOMINAL_BBOX,
    check_month_available,
    check_point_in_nominal_coverage,
)
from climateadapt.data.errors import (
    DataAccessError,
    DataIntegrityError,
    DataNotAvailableError,
    DownloadError,
    MissingDataError,
)
from climateadapt.data.periods import YearMonth, iter_months
from climateadapt.indicators.units import (
    days_in_month,
    kelvin_to_celsius,
    mean_daily_accumulation_m_to_monthly_mm,
)

logger = logging.getLogger(__name__)

DATASET_ID = "reanalysis-era5-land-monthly-means"
DATASET_NAME = "ERA5-Land monthly averaged data from 1950 to present"
PRODUCT_TYPE = "monthly_averaged_reanalysis"
AREA_HALF_WIDTH_DEG = 0.15  # request box half-width; guarantees several 0.1 degree points
GRID_MATCH_TOLERANCE_DEG = 0.075  # nearest grid point must be this close on each axis
NEGATIVE_NOISE_TOLERANCE_M_PER_DAY = 1e-6  # engineering assumption, see _convert_precipitation
MAX_NETCDF_BYTES = 200 * 1024 * 1024

CITATION = (
    "Mu\u00f1oz Sabater, J. (2019): ERA5-Land monthly averaged data from 1950 to present. "
    "Copernicus Climate Change Service (C3S) Climate Data Store (CDS). "
    "https://doi.org/10.24381/cds.68d2bb30. See also Mu\u00f1oz-Sabater, J. et al. (2021), "
    "ERA5-Land: a state-of-the-art global reanalysis dataset for land applications, "
    "Earth System Science Data 13, 4349."
)
DOI = "https://doi.org/10.24381/cds.68d2bb30"
LICENSE_NOTE = (
    "Copernicus licence terms apply. The dataset's terms of use must be accepted in the CDS "
    "before downloading. Acknowledge 'Copernicus Climate Change Service Information' and "
    "check the dataset page for the current licence text."
)

ERA5_LAND_LIMITATIONS: tuple[str, ...] = (
    "ERA5-Land is a reanalysis: land-surface model output forced by ERA5 atmospheric fields "
    "with no additional data assimilation. It is not a direct observation.",
    "Native resolution is about 9 km; the CDS distributes it on a 0.1 degree grid. A point "
    "value is the nearest grid point and is not comparable cell-for-cell with CHIRPS "
    "(0.05 degree). No elevation or local downscaling is applied.",
    "Precipitation is model-derived and inherits ERA5 forcing biases. It is not gauge-based. "
    "Monthly totals are converted from a mean daily accumulation: "
    "mm/month = mean(m/day) * 1000 * days in month.",
    "Temperature is the monthly mean of hourly 2 m temperature. Minimum and maximum "
    "temperatures are not available from the monthly means product.",
    "Recent months may come from a preliminary production stream (ERA5-Land-T) that cannot be "
    "distinguished in NetCDF output and could be revised. Prefer completed periods.",
    "Published validation covers selected regions. This project has performed no validation "
    "of ERA5-Land at the requested location.",
)


# ---------------------------------------------------------------- variable specifications


def _convert_temperature(raw: float, month: YearMonth) -> tuple[float, list[str]]:
    if not 150.0 <= raw <= 350.0:
        raise DataIntegrityError(
            f"Implausible 2 m temperature {raw} K for {month}; refusing to use it."
        )
    return kelvin_to_celsius(raw), []


def _convert_precipitation(raw: float, month: YearMonth) -> tuple[float, list[str]]:
    notes: list[str] = []
    value = raw
    if value < 0:
        # Packed accumulations can contain tiny negative noise. The tolerance below
        # (1e-6 m/day = 0.001 mm/day) is a conservative engineering assumption.
        if value < -NEGATIVE_NOISE_TOLERANCE_M_PER_DAY:
            raise DataIntegrityError(
                f"Unexpected negative precipitation {raw} m/day for {month}."
            )
        value = 0.0
        notes.append(
            "Tiny negative value (packing noise) within tolerance was set to 0 m/day."
        )
    if value > 1.0:
        raise DataIntegrityError(
            f"Implausible mean daily precipitation {raw} m/day for {month}; refusing to use it."
        )
    return mean_daily_accumulation_m_to_monthly_mm(value, month.year, month.month), notes


@dataclass(frozen=True)
class VariableSpec:
    cds_name: str
    file_short_names: tuple[str, ...]
    file_units: frozenset[str]
    output_units: str
    description: str
    convert: Callable[[float, YearMonth], tuple[float, list[str]]]


VARIABLES: dict[str, VariableSpec] = {
    "2m_temperature": VariableSpec(
        cds_name="2m_temperature",
        file_short_names=("t2m",),
        file_units=frozenset({"K"}),
        output_units="degC",
        description="Monthly mean 2 m air temperature",
        convert=_convert_temperature,
    ),
    "total_precipitation": VariableSpec(
        cds_name="total_precipitation",
        file_short_names=("tp",),
        file_units=frozenset({"m"}),
        output_units="mm/month",
        description="Monthly total precipitation derived from the mean daily accumulation",
        convert=_convert_precipitation,
    ),
}


# ---------------------------------------------------------------- models


class Era5Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    dataset_name: str
    product_type: str
    variable: str
    request: dict[str, Any]
    retrieved_at_utc: datetime
    raw_file_sha256: str
    raw_file_size_bytes: int
    raw_file_path: str
    delivered_as_zip: bool
    citation: str
    doi: str
    license_note: str


class Era5MonthRecord(BaseModel):
    """One cached point-month, with everything needed to trace it."""

    model_config = ConfigDict(extra="forbid")

    variable: str
    year: int
    month: int
    requested_latitude: float
    requested_longitude: float
    grid_point_latitude: float
    grid_point_longitude: float
    status: Literal["ok", "missing_value"]
    raw_value: float | None
    raw_units: str
    value: float | None
    units: str
    notes: list[str]
    provenance: Era5Provenance


class Era5MonthValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    month: int
    value: float | None
    status: Literal["ok", "missing_value"]
    notes: list[str]


class Era5PointSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    dataset_name: str
    variable: str
    description: str
    units: str
    requested_latitude: float
    requested_longitude: float
    grid_point_latitude: float
    grid_point_longitude: float
    values: list[Era5MonthValue]
    provenance: list[Era5Provenance]
    limitations: list[str]


# ---------------------------------------------------------------- NetCDF extraction

_TIME_NAMES = ("valid_time", "time")
_LAT_NAMES = ("latitude", "lat")
_LON_NAMES = ("longitude", "lon")


@dataclass(frozen=True)
class ExtractedPoint:
    grid_latitude: float
    grid_longitude: float
    units: str
    values: dict[YearMonth, float | None]


def _pick_variable(dataset: xr.Dataset, spec: VariableSpec) -> str:
    for name in spec.file_short_names:
        if name in dataset.data_vars:
            return name
    data_vars = list(dataset.data_vars)
    if len(data_vars) == 1:
        return str(data_vars[0])
    raise DataIntegrityError(
        f"Could not find variable {spec.file_short_names} in the NetCDF file "
        f"(found: {data_vars})."
    )


def _pick_name(dataset: xr.Dataset, candidates: tuple[str, ...], what: str) -> str:
    for name in candidates:
        if name in dataset.variables:
            return name
    raise DataIntegrityError(f"NetCDF file has no {what} coordinate (tried {candidates}).")


def extract_point(
    nc_path: Path, spec: VariableSpec, latitude: float, longitude: float
) -> ExtractedPoint:
    """Read the nearest grid point's monthly series from a CDS NetCDF file."""
    try:
        dataset = xr.open_dataset(nc_path)
    except (OSError, ValueError) as exc:
        raise DataIntegrityError(f"{nc_path.name} is not a readable NetCDF file: {exc}") from exc

    with dataset:
        var_name = _pick_variable(dataset, spec)
        data = dataset[var_name]

        units = data.attrs.get("units")
        if units is None:
            raise DataIntegrityError(
                f"Variable {var_name!r} has no 'units' attribute; cannot verify units."
            )
        if units not in spec.file_units:
            raise DataIntegrityError(
                f"Variable {var_name!r} has units {units!r}, expected one of "
                f"{sorted(spec.file_units)}; refusing to convert."
            )

        time_name = _pick_name(dataset, _TIME_NAMES, "time")
        lat_name = _pick_name(dataset, _LAT_NAMES, "latitude")
        lon_name = _pick_name(dataset, _LON_NAMES, "longitude")

        for name in (time_name, lat_name, lon_name):
            if name not in data.dims:
                data = data.expand_dims(name)
        for dim in [d for d in data.dims if d not in (time_name, lat_name, lon_name)]:
            if data.sizes[dim] != 1:
                raise DataIntegrityError(
                    f"Unexpected dimension {dim!r} of size {data.sizes[dim]} in the NetCDF file."
                )
            data = data.isel({dim: 0}, drop=True)

        lats = np.asarray(data[lat_name].values, dtype="float64")
        lons = np.asarray(data[lon_name].values, dtype="float64")
        lat_idx = int(np.argmin(np.abs(lats - latitude)))
        lon_diff = np.abs((lons - longitude + 180.0) % 360.0 - 180.0)
        lon_idx = int(np.argmin(lon_diff))
        if (
            abs(float(lats[lat_idx]) - latitude) > GRID_MATCH_TOLERANCE_DEG
            or float(lon_diff[lon_idx]) > GRID_MATCH_TOLERANCE_DEG
        ):
            raise DataIntegrityError(
                f"No grid point within {GRID_MATCH_TOLERANCE_DEG} degrees of "
                f"(lat={latitude}, lon={longitude}) in the downloaded file."
            )

        point = data.isel({lat_name: lat_idx, lon_name: lon_idx})
        raw = np.asarray(point.transpose(time_name).values, dtype="float64")
        times = np.asarray(data[time_name].values)

    if raw.ndim != 1 or raw.shape[0] != times.shape[0]:
        raise DataIntegrityError("Unexpected array shape after selecting the grid point.")
    if not np.issubdtype(times.dtype, np.datetime64):
        raise DataIntegrityError("Time coordinate could not be decoded as dates.")
    if np.isnat(times).any():
        raise DataIntegrityError("Time coordinate contains invalid (NaT) entries.")

    month_index = times.astype("datetime64[M]").astype("int64")
    values: dict[YearMonth, float | None] = {}
    for index, value in zip(month_index, raw, strict=True):
        month = YearMonth(int(1970 + index // 12), int(index % 12 + 1))
        if month in values:
            raise DataIntegrityError(f"Duplicate time step for {month} in the NetCDF file.")
        number = float(value)
        if math.isinf(number):
            raise DataIntegrityError(f"Infinite value at {month} in the NetCDF file.")
        values[month] = None if math.isnan(number) else number

    grid_lon = round(((float(lons[lon_idx]) + 180.0) % 360.0) - 180.0, 6)
    return ExtractedPoint(
        grid_latitude=round(float(lats[lat_idx]), 6),
        grid_longitude=grid_lon,
        units=str(units),
        values=values,
    )


# ---------------------------------------------------------------- downloading


class CdsDownloader(Protocol):
    """Anything that can fulfil a CDS request into a file. Faked in tests."""

    def download(self, dataset: str, request: Mapping[str, Any], target: Path) -> None: ...


def _translate_cds_error(exc: Exception) -> DataAccessError:
    text = str(exc).strip()[:500]
    lowered = text.lower()
    if any(
        phrase in lowered
        for phrase in ("not available yet", "latest date available", "none of the data")
    ):
        return DataNotAvailableError(
            f"The CDS reports that the requested ERA5-Land period is not available yet: {text}"
        )
    return DownloadError(
        f"CDS request failed ({type(exc).__name__}): {text}. If this is an authentication or "
        "licence error: create a CDS account, put your personal access token in ~/.cdsapirc, "
        "and accept the terms of use on the dataset's CDS page."
    )


class CdsApiDownloader:
    """Adapter around the official ``cdsapi`` client.

    Credentials are read by cdsapi itself (normally from ~/.cdsapirc).
    """

    def __init__(self, *, client_factory: Callable[[], Any] | None = None) -> None:
        self._client_factory = client_factory
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                try:
                    import cdsapi
                except ImportError as exc:
                    raise DataAccessError(
                        "The 'cdsapi' package is not installed. Run `uv sync --extra dev`."
                    ) from exc
                self._client = cdsapi.Client()
        return self._client

    def download(self, dataset: str, request: Mapping[str, Any], target: Path) -> None:
        try:
            self._get_client().retrieve(dataset, dict(request)).download(str(target))
        except DataAccessError:
            raise
        except Exception as exc:  # third-party boundary: cdsapi raises many exception types
            raise _translate_cds_error(exc) from exc


# ---------------------------------------------------------------- store


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def group_months_for_requests(months: list[YearMonth]) -> list[tuple[list[int], list[int]]]:
    """Group months into (years, month_numbers) requests whose product is EXACTLY the need.

    Years that need the same set of calendar months share one request, so a request never
    includes a month that was not asked for.
    """
    by_year: dict[int, set[int]] = {}
    for month in months:
        by_year.setdefault(month.year, set()).add(month.month)
    groups: dict[frozenset[int], list[int]] = {}
    for year, month_set in sorted(by_year.items()):
        groups.setdefault(frozenset(month_set), []).append(year)
    return [(years, sorted(month_set)) for month_set, years in groups.items()]


def build_request(
    spec: VariableSpec, years: list[int], months: list[int], latitude: float, longitude: float
) -> dict[str, Any]:
    """Build the CDS request dict (area is [north, west, south, east])."""
    north = min(90.0, latitude + AREA_HALF_WIDTH_DEG)
    south = max(-90.0, latitude - AREA_HALF_WIDTH_DEG)
    west = max(-180.0, longitude - AREA_HALF_WIDTH_DEG)
    east = min(180.0, longitude + AREA_HALF_WIDTH_DEG)
    return {
        "product_type": [PRODUCT_TYPE],
        "variable": [spec.cds_name],
        "year": [f"{year:04d}" for year in years],
        "month": [f"{month:02d}" for month in months],
        "time": ["00:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": [round(north, 4), round(west, 4), round(south, 4), round(east, 4)],
    }


class Era5LandMonthlyStore:
    """Download-and-cache layer producing per-month point records."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        downloader: CdsDownloader,
        allow_downloads: bool = True,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._downloader = downloader
        self._allow_downloads = allow_downloads
        self._today = today

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def assert_month_available(self, month: YearMonth) -> None:
        check_month_available(
            month,
            today=self._today(),
            first_month=ERA5_LAND_FIRST_MONTH,
            dataset="ERA5-Land monthly means",
        )

    def _record_path(
        self, spec: VariableSpec, lat_key: float, lon_key: float, month: YearMonth
    ) -> Path:
        return (
            self._cache_dir
            / "monthly"
            / spec.cds_name
            / f"lat{lat_key:.4f}_lon{lon_key:.4f}"
            / f"{month}.json"
        )

    def _load_record(
        self,
        path: Path,
        spec: VariableSpec,
        lat_key: float,
        lon_key: float,
        month: YearMonth,
    ) -> Era5MonthRecord | None:
        if not path.exists():
            return None
        try:
            record = Era5MonthRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Unreadable cached record %s; ignoring it.", path)
            return None
        if (
            record.variable != spec.cds_name
            or (record.year, record.month) != (month.year, month.month)
            or not math.isclose(record.requested_latitude, lat_key, abs_tol=1e-9)
            or not math.isclose(record.requested_longitude, lon_key, abs_tol=1e-9)
        ):
            logger.warning("Cached record %s does not match its request; ignoring it.", path)
            return None
        return record

    def get_records(
        self, spec: VariableSpec, latitude: float, longitude: float, months: list[YearMonth]
    ) -> list[Era5MonthRecord]:
        """Return one record per requested month, downloading only what is missing."""
        for month in months:
            self.assert_month_available(month)

        lat_key, lon_key = round(latitude, 4), round(longitude, 4)
        records: dict[YearMonth, Era5MonthRecord] = {}
        missing: list[YearMonth] = []
        for month in months:
            path = self._record_path(spec, lat_key, lon_key, month)
            cached = self._load_record(path, spec, lat_key, lon_key, month)
            if cached is not None:
                records[month] = cached
            else:
                missing.append(month)

        if missing:
            if not self._allow_downloads:
                raise DataNotAvailableError(
                    f"{len(missing)} ERA5-Land month(s) are not in the local cache and "
                    "downloads are disabled (CLIMATEADAPT_ALLOW_DOWNLOADS=false): "
                    + ", ".join(str(m) for m in missing[:6])
                    + (" ..." if len(missing) > 6 else "")
                )
            for years, month_numbers in group_months_for_requests(missing):
                records.update(
                    self._download_group(spec, lat_key, lon_key, years, month_numbers)
                )

        return [records[month] for month in months]

    def _download_group(
        self,
        spec: VariableSpec,
        lat_key: float,
        lon_key: float,
        years: list[int],
        month_numbers: list[int],
    ) -> dict[YearMonth, Era5MonthRecord]:
        request = build_request(spec, years, month_numbers, lat_key, lon_key)
        key = hashlib.sha256(
            json.dumps({"dataset": DATASET_ID, "request": request}, sort_keys=True).encode()
        ).hexdigest()[:16]
        raw_dir = self._cache_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        download_path = raw_dir / f"{key}.download"
        nc_path = raw_dir / f"{key}.nc"

        logger.info("Requesting %s %s for years %s months %s", DATASET_ID, spec.cds_name, years, month_numbers)
        succeeded = False
        try:
            self._downloader.download(DATASET_ID, request, download_path)
            if not download_path.exists():
                raise DownloadError("The downloader reported success but produced no file.")
            delivered_as_zip = self._finalize_download(download_path, nc_path)
            sha256, size = _sha256_file(nc_path)
            extracted = extract_point(nc_path, spec, lat_key, lon_key)
            succeeded = True
        finally:
            download_path.unlink(missing_ok=True)
            if not succeeded:
                nc_path.unlink(missing_ok=True)

        provenance = Era5Provenance(
            dataset_id=DATASET_ID,
            dataset_name=DATASET_NAME,
            product_type=PRODUCT_TYPE,
            variable=spec.cds_name,
            request=request,
            retrieved_at_utc=datetime.now(UTC),
            raw_file_sha256=sha256,
            raw_file_size_bytes=size,
            raw_file_path=str(nc_path),
            delivered_as_zip=delivered_as_zip,
            citation=CITATION,
            doi=DOI,
            license_note=LICENSE_NOTE,
        )

        result: dict[YearMonth, Era5MonthRecord] = {}
        for year in years:
            for month_number in month_numbers:
                month = YearMonth(year, month_number)
                if month not in extracted.values:
                    raise DataIntegrityError(
                        f"Requested month {month} is missing from the downloaded file."
                    )
                raw_value = extracted.values[month]
                if raw_value is None:
                    value: float | None = None
                    notes: list[str] = []
                else:
                    value, notes = spec.convert(raw_value, month)
                record = Era5MonthRecord(
                    variable=spec.cds_name,
                    year=year,
                    month=month_number,
                    requested_latitude=lat_key,
                    requested_longitude=lon_key,
                    grid_point_latitude=extracted.grid_latitude,
                    grid_point_longitude=extracted.grid_longitude,
                    status="ok" if value is not None else "missing_value",
                    raw_value=raw_value,
                    raw_units=extracted.units,
                    value=value,
                    units=spec.output_units,
                    notes=notes,
                    provenance=provenance,
                )
                _atomic_write_text(
                    self._record_path(spec, lat_key, lon_key, month),
                    record.model_dump_json(indent=2),
                )
                result[month] = record
        return result

    @staticmethod
    def _finalize_download(download_path: Path, nc_path: Path) -> bool:
        """Move the downloaded file into place, unpacking a zip if CDS delivered one."""
        if zipfile.is_zipfile(download_path):
            with zipfile.ZipFile(download_path) as archive:
                members = [m for m in archive.infolist() if m.filename.lower().endswith(".nc")]
                if len(members) != 1:
                    raise DataIntegrityError(
                        "Expected exactly one NetCDF file in the downloaded archive, "
                        f"found {len(members)}."
                    )
                member = members[0]
                if member.file_size > MAX_NETCDF_BYTES:
                    raise DataIntegrityError("NetCDF file in the archive is unexpectedly large.")
                with archive.open(member) as source, open(nc_path, "wb") as target:
                    shutil.copyfileobj(source, target)
            return True
        os.replace(download_path, nc_path)
        return False


# ---------------------------------------------------------------- client


class Era5LandClient:
    """Point time-series access to ERA5-Land monthly means."""

    def __init__(self, store: Era5LandMonthlyStore) -> None:
        self._store = store

    @property
    def store(self) -> Era5LandMonthlyStore:
        return self._store

    def monthly_point_series(
        self,
        variable: str,
        latitude: float,
        longitude: float,
        start: YearMonth,
        end: YearMonth,
    ) -> Era5PointSeries:
        """Return monthly values for the nearest ERA5-Land grid point.

        All validation runs BEFORE any download.
        """
        spec = VARIABLES.get(variable)
        if spec is None:
            raise ValueError(
                f"Unsupported ERA5-Land variable {variable!r}; supported: {sorted(VARIABLES)}."
            )
        lat, lon = check_point_in_nominal_coverage(
            latitude, longitude, ERA5_LAND_NOMINAL_BBOX, dataset="ERA5-Land"
        )
        months = list(iter_months(start, end))
        for month in months:
            self._store.assert_month_available(month)

        records = self._store.get_records(spec, lat, lon, months)

        first = records[0]
        for record in records[1:]:
            if not (
                math.isclose(
                    record.grid_point_latitude, first.grid_point_latitude, abs_tol=1e-6
                )
                and math.isclose(
                    record.grid_point_longitude, first.grid_point_longitude, abs_tol=1e-6
                )
            ):
                raise DataIntegrityError(
                    "Grid point differs between months in the series; refusing to combine."
                )

        provenance: dict[tuple[str, str], Era5Provenance] = {}
        for record in records:
            prov = record.provenance
            provenance.setdefault((prov.raw_file_sha256, prov.raw_file_path), prov)

        return Era5PointSeries(
            dataset_id=DATASET_ID,
            dataset_name=DATASET_NAME,
            variable=spec.cds_name,
            description=spec.description,
            units=spec.output_units,
            requested_latitude=lat,
            requested_longitude=lon,
            grid_point_latitude=first.grid_point_latitude,
            grid_point_longitude=first.grid_point_longitude,
            values=[
                Era5MonthValue(
                    year=r.year,
                    month=r.month,
                    value=r.value,
                    status=r.status,
                    notes=list(r.notes),
                )
                for r in records
            ],
            provenance=list(provenance.values()),
            limitations=list(ERA5_LAND_LIMITATIONS),
        )


def _complete_values(series: Era5PointSeries) -> list[tuple[int, int, float]]:
    if not series.values:
        raise ValueError("Series is empty.")
    missing = [f"{v.year:04d}-{v.month:02d}" for v in series.values if v.value is None]
    if missing:
        raise MissingDataError(
            "Cannot aggregate because values are missing for: "
            + ", ".join(missing)
            + ". Partial aggregates would be misleading, so none is returned."
        )
    return [(v.year, v.month, float(v.value)) for v in series.values if v.value is not None]


def total_precipitation_mm(series: Era5PointSeries) -> float:
    """Sum monthly precipitation (mm/month). Strict: any missing month raises."""
    if series.units != "mm/month":
        raise ValueError(f"Expected a precipitation series (mm/month), got {series.units!r}.")
    return math.fsum(value for _, _, value in _complete_values(series))


def day_weighted_mean_temperature_c(series: Era5PointSeries) -> float:
    """Mean temperature over the window, weighting each month by its number of days."""
    if series.units != "degC":
        raise ValueError(f"Expected a temperature series (degC), got {series.units!r}.")
    entries = _complete_values(series)
    weights = [days_in_month(year, month) for year, month, _ in entries]
    total = math.fsum(value * weight for (_, _, value), weight in zip(entries, weights, strict=True))
    return total / sum(weights)


def build_era5_land_client(
    settings: Settings, *, downloader: CdsDownloader | None = None
) -> Era5LandClient:
    """Construct a client from application settings."""
    store = Era5LandMonthlyStore(
        cache_dir=settings.data_dir / "cache" / "era5_land",
        downloader=downloader if downloader is not None else CdsApiDownloader(),
        allow_downloads=settings.allow_downloads,
    )
    return Era5LandClient(store)