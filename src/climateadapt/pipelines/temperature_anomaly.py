"""ERA5-Land temperature anomaly for a point: connector + the tested pure calculation.

Same structure and safeguards as ``pipelines/spi_era5.py``: validate everything first, read the
target window, group the reference requests, refuse to mix grid points, and report any use of
the opt-in land fallback prominently. Window assembly is shared via
``pipelines/era5_windows.py`` (P04, KI-16).
"""

from __future__ import annotations

from typing import Literal

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
    IncompleteWindowError,
    validate_parameters,
)
from climateadapt.indicators.temperature import compute_temperature_anomaly
from climateadapt.pipelines.era5_windows import (
    fetch_era5_window_values,
    plan_era5_reference_windows,
)
from climateadapt.pipelines.spi import (
    DEFAULT_REFERENCE_END_YEAR,
    DEFAULT_REFERENCE_START_YEAR,
    RECOMMENDED_REFERENCE_YEARS,
    ExcludedReferenceYear,
)
from climateadapt.pipelines.spi_era5 import Era5RawFile

VARIABLE = "2m_temperature"

TEMPERATURE_LIMITATIONS: tuple[str, ...] = (
    "Anomaly = target window mean temperature minus the mean of the same calendar window over "
    "the reference years, in degC (a difference, not a percentage). Window means are "
    "day-weighted averages of ERA5-Land monthly means of hourly 2 m temperature.",
    "The reference mean includes any warming trend inside the reference period; the anomaly is "
    "relative to the reference-period average, not to a detrended or pre-industrial baseline.",
    "The standardized anomaly divides by the sample standard deviation of the reference window "
    "means and is uncertain with about 30 values. The percentile rank is empirical (mid-rank).",
    "Monthly means cannot reveal heat waves, frost, or the timing of extremes, and a temperature "
    "anomaly is not a drought indicator by itself; it is context for evaporative demand and "
    "crop heat stress.",
)


class Era5TemperatureAnomalyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator: Literal["temperature_window_anomaly"] = "temperature_window_anomaly"
    data_source: str
    timescale_months: int
    target_window_start: str
    target_window_end: str
    window_mean_c: float
    reference_mean_c: float
    anomaly_c: float
    reference_sd_c: float | None
    standardized_anomaly: float | None
    percentile_rank: float
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
    raw_files: list[Era5RawFile]
    citation: str
    doi: str
    license_note: str
    limitations: list[str]


def era5_land_temperature_anomaly(
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
) -> Era5TemperatureAnomalyResult:
    """Compute the ERA5-Land temperature window anomaly for a point."""
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
            "The anomaly cannot be computed from an incomplete window. If the nearest "
            "ERA5-Land grid point is masked (for example sea), retry with land_fallback_max_km."
        ),
    )
    target_series = all_series[0]
    reference = all_series[0]

    try:
        result = compute_temperature_anomaly(
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
        for year in result.reference_years_unavailable
    ]
    n_used = len(result.reference_years_used)
    fallback = target_series.land_fallback

    limitations = list(TEMPERATURE_LIMITATIONS)
    if fallback is not None and fallback.used and fallback.warning:
        limitations.insert(0, fallback.warning)
    if n_used < RECOMMENDED_REFERENCE_YEARS:
        limitations.append(
            f"The reference period has only {n_used} usable years; climate normals conventionally "
            f"use {RECOMMENDED_REFERENCE_YEARS} years, so the reference mean and spread are "
            "less stable."
        )
    if result.target_in_reference_period:
        limitations.append(
            "The target window lies inside the reference period, so it contributed to its own "
            "reference mean."
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

    return Era5TemperatureAnomalyResult(
        data_source=f"{DATASET_NAME} ({DATASET_ID})",
        timescale_months=k,
        target_window_start=str(target_months[0]),
        target_window_end=str(target_months[-1]),
        window_mean_c=result.window_mean_c,
        reference_mean_c=result.reference_mean_c,
        anomaly_c=result.anomaly_c,
        reference_sd_c=result.reference_sd_c,
        standardized_anomaly=result.standardized_anomaly,
        percentile_rank=result.percentile_rank,
        message=result.reason,
        requested_latitude=lat,
        requested_longitude=lon,
        grid_point_latitude=reference.grid_point_latitude,
        grid_point_longitude=reference.grid_point_longitude,
        land_fallback=fallback,
        reference_start_year=reference_start_year,
        reference_end_year=reference_end_year,
        min_reference_years=min_reference_years,
        reference_years_used=n_used,
        reference_years_included=result.reference_years_used,
        reference_years_excluded=excluded,
        target_in_reference_period=result.target_in_reference_period,
        raw_files=list(raw_files.values()),
        citation=CITATION,
        doi=DOI,
        license_note=LICENSE_NOTE,
        limitations=limitations,
    )
