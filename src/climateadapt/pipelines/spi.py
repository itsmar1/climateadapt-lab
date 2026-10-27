"""CHIRPS-based SPI for a point: connector + the tested pure SPI calculation."""

from __future__ import annotations

import math
from itertools import chain
from typing import Literal

from pydantic import BaseModel, ConfigDict

from climateadapt.data.chirps import BOUNDARY_LIMITATION, CHIRPS_V3_LIMITATIONS, ChirpsV3Client
from climateadapt.data.coverage import CHIRPS_V3_FINAL_FIRST_MONTH, check_point_in_nominal_coverage
from climateadapt.data.errors import DataIntegrityError, MissingDataError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    DEFAULT_MIN_REFERENCE_YEARS,
    METHOD,
    IncompleteWindowError,
    compute_spi,
    validate_parameters,
    window_months,
)
from climateadapt.pipelines.rainfall_anomaly import SourceFileRecord

DATA_SOURCE = "CHIRPS v3.0 Final, monthly, 0.05 degree grid"
DEFAULT_REFERENCE_START_YEAR = 1991
DEFAULT_REFERENCE_END_YEAR = 2020
RECOMMENDED_REFERENCE_YEARS = 30

SPI_LIMITATIONS: tuple[str, ...] = (
    "SPI expresses precipitation relative to the fitted reference-period distribution only. "
    "It does not include temperature, evapotranspiration, soil moisture, or crop impacts and "
    "is not a measure of agricultural drought damage.",
    "Method: CHIRPS v3 Final monthly window totals; a gamma distribution is fitted per "
    "calendar month to the non-zero totals (Thom 1958 approximation of maximum likelihood); "
    "zeros are a point mass q = zeros / reference years; the cumulative probability is mapped "
    "to a standard normal quantile (McKee et al. 1993; WMO-No. 1090).",
    "SPI depends on the chosen reference period; values are not comparable across different "
    "reference periods or precipitation products.",
    "The gamma fit is not goodness-of-fit tested here. Values beyond about +/-2 are driven by "
    "the fitted tail and are uncertain, especially with short reference periods.",
)


class ExcludedReferenceYear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    reason: str


class ChirpsSpiResult(BaseModel):
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
    grid_cell_center_latitude: float
    grid_cell_center_longitude: float
    point_on_cell_boundary: bool
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
    source_files: list[SourceFileRecord]
    citation: str
    doi: str
    license_note: str
    limitations: list[str]


def chirps_spi(
    client: ChirpsV3Client,
    *,
    latitude: float,
    longitude: float,
    target_end_month: YearMonth,
    timescale_months: int,
    reference_start_year: int = DEFAULT_REFERENCE_START_YEAR,
    reference_end_year: int = DEFAULT_REFERENCE_END_YEAR,
    min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
) -> ChirpsSpiResult:
    """Compute SPI from CHIRPS v3 Final for a point, window, and reference period."""
    validate_parameters(
        timescale_months, reference_start_year, reference_end_year, min_reference_years
    )
    lat, lon = check_point_in_nominal_coverage(latitude, longitude)
    k = timescale_months

    target_months = window_months(target_end_month, k)
    windows: dict[int, list[YearMonth]] = {}
    pipeline_reasons: dict[int, str] = {}
    for year in range(reference_start_year, reference_end_year + 1):
        months = window_months(YearMonth(year, target_end_month.month), k)
        if months[0] < CHIRPS_V3_FINAL_FIRST_MONTH:
            pipeline_reasons[year] = (
                f"the window starts at {months[0]}, before the CHIRPS v3 Final record begins "
                f"({CHIRPS_V3_FINAL_FIRST_MONTH})"
            )
            continue
        windows[year] = months

    # Fail fast: validate every month BEFORE any network access.
    for month in chain(target_months, *windows.values()):
        client.store.assert_month_available(month)

    client.prefetch(lat, lon, target_months)
    target_series = client.monthly_point_series(lat, lon, target_months[0], target_months[-1])
    missing = [
        f"{v.year:04d}-{v.month:02d}" for v in target_series.values if v.precipitation_mm is None
    ]
    if missing:
        raise MissingDataError(
            "The target window has no value for: " + ", ".join(missing) + ". SPI cannot be "
            "computed from an incomplete window."
        )

    needed = sorted({month for months in windows.values() for month in months})
    if needed:
        client.prefetch(lat, lon, needed)

    monthly: dict[YearMonth, float | None] = {}
    all_series = [target_series]
    for series in [target_series]:
        for v in series.values:
            monthly[YearMonth(v.year, v.month)] = v.precipitation_mm
    for months in windows.values():
        series = client.monthly_point_series(lat, lon, months[0], months[-1])
        all_series.append(series)
        for v in series.values:
            monthly[YearMonth(v.year, v.month)] = v.precipitation_mm

    reference = all_series[0]
    for series in all_series[1:]:
        if not (
            math.isclose(
                series.pixel_center_latitude, reference.pixel_center_latitude, abs_tol=1e-9
            )
            and math.isclose(
                series.pixel_center_longitude, reference.pixel_center_longitude, abs_tol=1e-9
            )
        ):
            raise DataIntegrityError("Grid cell differs between windows; refusing to combine them.")

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
    on_boundary = any(series.point_on_cell_boundary for series in all_series)

    limitations = list(SPI_LIMITATIONS)
    if on_boundary:
        limitations.insert(0, BOUNDARY_LIMITATION)
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
    limitations.extend(CHIRPS_V3_LIMITATIONS)

    files: dict[tuple[int, int], SourceFileRecord] = {}
    for series in all_series:
        for prov in series.provenance:
            files[(prov.year, prov.month)] = SourceFileRecord(
                year=prov.year,
                month=prov.month,
                source_url=prov.source_url,
                access_mode=prov.access_mode,
                sha256=prov.sha256,
                size_bytes=prov.size_bytes,
                remote_etag=prov.remote_etag,
                remote_last_modified=prov.remote_last_modified,
                retrieved_at_utc=prov.retrieved_at_utc,
            )

    fit = computation.fit
    first_prov = target_series.provenance[0]
    return ChirpsSpiResult(
        status=computation.status,
        data_source=DATA_SOURCE,
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
        grid_cell_center_latitude=reference.pixel_center_latitude,
        grid_cell_center_longitude=reference.pixel_center_longitude,
        point_on_cell_boundary=on_boundary,
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
        source_files=[files[key] for key in sorted(files)],
        citation=first_prov.citation,
        doi=first_prov.doi,
        license_note=first_prov.license_note,
        limitations=limitations,
    )