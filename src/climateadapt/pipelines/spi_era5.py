"""ERA5-Land-based SPI for a point: connector + the tested pure SPI calculation.

Mirrors ``pipelines/spi.py`` (CHIRPS). Differences: data come from ERA5-Land monthly means
(0.1 degree reanalysis, 1950 onwards) through the Copernicus CDS, and a masked nearest grid
point can be handled by the opt-in land fallback. The SAME grid point must serve every window;
otherwise the run is refused. Window assembly is shared via ``pipelines/era5_windows.py``
(P04, KI-16).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from climateadapt.data.coverage import (
    ERA5_LAND_NOMINAL_BBOX,
    check_point_in_nominal_coverage,
)
from climateadapt.data.era5_land import (
    CITATION,
    DATASET_ID,
    DATASET_NAME,
    DOI,
    ERA5_LAND_LIMITATIONS,
    LICENSE_NOTE,
    VARIABLES,
    Era5LandClient,
    LandFallback,
)
from climateadapt.data.errors import MissingDataError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    DEFAULT_MIN_REFERENCE_YEARS,
    METHOD,
    IncompleteWindowError,
    compute_spi,
    validate_parameters,
)
from climateadapt.pipelines.era5_windows import (
    fetch_era5_window_values,
    plan_era5_reference_windows,
)
from climateadapt.pipelines.spi import (
    DEFAULT_REFERENCE_END_YEAR,
    DEFAULT_REFERENCE_START_YEAR,
    RECOMMENDED_REFERENCE_YEARS,
    SPI_LIMITATIONS,
    ExcludedReferenceYear,
)

VARIABLE = "total_precipitation"


class Era5RawFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    request: dict[str, Any]
    raw_file_sha256: str
    raw_file_size_bytes: int
    delivered_as_zip: bool
    retrieved_at_utc: datetime


class Era5SpiResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "undefined"]
    indicator: Literal["standardized_precipitation_index"] = "standardized_precipitation_index"
    data_source: str
    method: str
    timescale_months: int
    target_window_start: str
    target_window_end: str
    window_total_mm: float
    spi: float | None
    cumulative_probability: float | None
    message: str | None
    requested_latitude: float
    requested_longitude: float
    grid_point_latitude: float
    grid_point_longitude: float
    land_fallback: LandFallback | None
    reference_start_year: int
    reference_end_year: int
    min_reference_years: int
    reference_years_used: int
    reference_years_included: list[int]
    reference_years_excluded: list[ExcludedReferenceYear]
    target_in_reference_period: bool
    gamma_shape: float | None
    gamma_scale_mm: float | None
    zero_probability: float | None
    reference_zero_count: int | None
    reference_nonzero_count: int | None
    reference_spi_mean: float | None
    reference_spi_std: float | None
    raw_files: list[Era5RawFile]
    citation: str
    doi: str
    license_note: str
    limitations: list[str]


def era5_land_spi(
    client: Era5LandClient,
    *,
    latitude: float,
    longitude: float,
    target_end_month: YearMonth,
    timescale_months: int,
    reference_start_year: int = DEFAULT_REFERENCE_START_YEAR,
    reference_end_year: int = DEFAULT_REFERENCE_END_YEAR,
    min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
    land_fallback_max_km: float | None = None,
) -> Era5SpiResult:
    """Compute SPI from ERA5-Land monthly precipitation for a point."""
    validate_parameters(
        timescale_months, reference_start_year, reference_end_year, min_reference_years
    )
    lat, lon = check_point_in_nominal_coverage(
        latitude, longitude, ERA5_LAND_NOMINAL_BBOX, dataset="ERA5-Land"
    )
    k = timescale_months
    spec = VARIABLES[VARIABLE]

    target_months, windows, pipeline_reasons = plan_era5_reference_windows(
        target_end_month, k, reference_start_year, reference_end_year
    )
    monthly, all_series = fetch_era5_window_values(
        client,
        spec,
        lat,
        lon,
        target_months,
        windows,
        land_fallback_max_km=land_fallback_max_km,
        incomplete_window_message=(
            "SPI cannot be computed from an incomplete window. If the nearest ERA5-Land "
            "grid point is masked (for example sea), retry with land_fallback_max_km."
        ),
    )
    reference = all_series[0]

    try:
        computation = compute_spi(
            monthly,
            target_end_month,
            k,
            reference_start_year,
            reference_end_year,
            min_reference_years=min_reference_years,
        )
    except IncompleteWindowError as exc:
        raise MissingDataError(str(exc)) from exc

    excluded = [
        ExcludedReferenceYear(
            year=year,
            reason=pipeline_reasons.get(
                year, "one or more months in the window have no value (missing data)"
            ),
        )
        for year in computation.reference_years_unavailable
    ]
    n_used = len(computation.reference_years_used)
    fallback = all_series[0].land_fallback

    limitations = list(SPI_LIMITATIONS)
    if fallback is not None and fallback.used and fallback.warning:
        limitations.insert(0, fallback.warning)
    if n_used < RECOMMENDED_REFERENCE_YEARS:
        limitations.append(
            f"The reference period has only {n_used} usable years. WMO-No. 1090 recommends at "
            f"least {RECOMMENDED_REFERENCE_YEARS} years of monthly data, so the fitted "
            "distribution and extreme SPI values are less reliable."
        )
    if computation.target_in_reference_period:
        limitations.append(
            "The target window lies inside the reference period, so it contributed to its own "
            "calibration."
        )
    if excluded:
        limitations.append(
            f"{len(excluded)} reference year(s) were excluded because their windows are "
            "incomplete or unavailable."
        )
    limitations.extend(ERA5_LAND_LIMITATIONS)

    raw_files: dict[tuple[str, str], Era5RawFile] = {}
    for series in all_series:
        for prov in series.provenance:
            raw_files.setdefault(
                (prov.raw_file_sha256, prov.raw_file_path),
                Era5RawFile(
                    dataset_id=prov.dataset_id,
                    request=prov.request,
                    raw_file_sha256=prov.raw_file_sha256,
                    raw_file_size_bytes=prov.raw_file_size_bytes,
                    delivered_as_zip=prov.delivered_as_zip,
                    retrieved_at_utc=prov.retrieved_at_utc,
                ),
            )

    fit = computation.fit
    return Era5SpiResult(
        status=computation.status,
        data_source=f"{DATASET_NAME} ({DATASET_ID})",
        method=METHOD,
        timescale_months=k,
        target_window_start=str(target_months[0]),
        target_window_end=str(target_months[-1]),
        window_total_mm=computation.window_total_mm,
        spi=computation.spi,
        cumulative_probability=computation.cumulative_probability,
        message=computation.reason,
        requested_latitude=lat,
        requested_longitude=lon,
        grid_point_latitude=reference.grid_point_latitude,
        grid_point_longitude=reference.grid_point_longitude,
        land_fallback=fallback,
        reference_start_year=reference_start_year,
        reference_end_year=reference_end_year,
        min_reference_years=min_reference_years,
        reference_years_used=n_used,
        reference_years_included=computation.reference_years_used,
        reference_years_excluded=excluded,
        target_in_reference_period=computation.target_in_reference_period,
        gamma_shape=fit.shape if fit else None,
        gamma_scale_mm=fit.scale if fit else None,
        zero_probability=fit.zero_probability if fit else None,
        reference_zero_count=fit.n_zero if fit else None,
        reference_nonzero_count=fit.n_nonzero if fit else None,
        reference_spi_mean=computation.reference_spi_mean,
        reference_spi_std=computation.reference_spi_std,
        raw_files=list(raw_files.values()),
        citation=CITATION,
        doi=DOI,
        license_note=LICENSE_NOTE,
        limitations=limitations,
    )
