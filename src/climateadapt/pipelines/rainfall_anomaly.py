"""CHIRPS-based precipitation percentage anomaly.

Method
------
* The observation window is ``window_months`` whole calendar months starting at
  ``observed_start``. It may cross a year boundary (e.g. Nov-Jan).
* For each baseline year Y, the baseline window covers the SAME calendar months,
  starting at (Y, observed_start.month). The window's total is the sum of its months.
* A baseline year with ANY missing month is excluded (never imputed, never partially
  summed). Fewer than ``min_baseline_years`` complete years raises an error.
* baseline_mean = mean of the complete yearly window totals.
* The anomaly uses the tested indicator in ``climateadapt.indicators.rainfall``.

This is still the simple percentage anomaly: NOT a calibrated drought index.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from climateadapt.data.chirps import (
    CHIRPS_V3_LIMITATIONS,
    ChirpsV3Client,
    accumulated_total_mm,
)
from climateadapt.data.coverage import check_point_in_nominal_coverage
from climateadapt.data.errors import DataIntegrityError, MissingDataError
from climateadapt.data.periods import YearMonth, iter_months
from climateadapt.indicators.rainfall import (
    FORMULA,
    AnomalyUndefinedError,
    Direction,
    anomaly_direction,
    percentage_anomaly,
)

MIN_BASELINE_YEARS_DEFAULT = 10
CLIMATOLOGY_REFERENCE_YEARS = 30
DATA_SOURCE = "CHIRPS v3.0 Final, monthly, 0.05 degree grid"

PIPELINE_LIMITATIONS: tuple[str, ...] = (
    "This is a simple percentage anomaly of accumulated precipitation, not a calibrated "
    "drought index.",
    "It must not be used alone to classify drought severity; the same percentage anomaly "
    "has different meaning in different climates and seasons.",
    "The observation window and every baseline window cover the same calendar months "
    "(whole months only) and come from the same product (CHIRPS v3 Final).",
    "The baseline is the mean of complete yearly window totals; years with any missing "
    "month are excluded, not imputed.",
)


class InsufficientBaselineError(Exception):
    """Too few complete baseline years to compute a baseline mean."""


class SourceFileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    month: int
    source_url: str
    sha256: str
    size_bytes: int
    retrieved_at_utc: datetime


class YearTotal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_year: int
    window_start: str
    window_end: str
    total_mm: float


class ExcludedYear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_year: int
    window_start: str
    window_end: str
    reason: str


class ChirpsRainfallAnomalyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "undefined"]
    indicator: Literal["precipitation_percentage_anomaly"] = "precipitation_percentage_anomaly"
    data_source: str
    percentage_anomaly: float | None
    absolute_difference_mm: float
    direction: Direction
    observed_total_mm: float
    baseline_mean_mm: float
    formula: str
    requested_latitude: float
    requested_longitude: float
    grid_cell_center_latitude: float
    grid_cell_center_longitude: float
    observed_window_start: str
    observed_window_end: str
    window_months: int
    baseline_start_year: int
    baseline_end_year: int
    min_baseline_years: int
    baseline_years_used: int
    baseline_totals: list[YearTotal]
    baseline_excluded: list[ExcludedYear]
    baseline_includes_observed_period: bool
    message: str | None = None
    source_files: list[SourceFileRecord]
    citation: str
    doi: str
    license_note: str
    limitations: list[str]


def season_window(start: YearMonth, n_months: int) -> tuple[YearMonth, YearMonth]:
    """Return (first, last) month of a window of ``n_months`` starting at ``start``."""
    if isinstance(n_months, bool) or not isinstance(n_months, int) or not 1 <= n_months <= 12:
        raise ValueError(f"window_months must be an integer from 1 to 12, got {n_months!r}.")
    end = start
    for _ in range(n_months - 1):
        end = end.next()
    return start, end


def _require_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, got {value!r}.")
    return value


def chirps_rainfall_anomaly(
    client: ChirpsV3Client,
    *,
    latitude: float,
    longitude: float,
    observed_start: YearMonth,
    window_months_count: int,
    baseline_start_year: int,
    baseline_end_year: int,
    min_baseline_years: int = MIN_BASELINE_YEARS_DEFAULT,
) -> ChirpsRainfallAnomalyResult:
    """Compute the CHIRPS-based percentage anomaly for a point and calendar window."""
    obs_start, obs_end = season_window(observed_start, window_months_count)
    first_year = _require_int("baseline_start_year", baseline_start_year)
    last_year = _require_int("baseline_end_year", baseline_end_year)
    min_years = _require_int("min_baseline_years", min_baseline_years)
    if last_year < first_year:
        raise ValueError("baseline_end_year must not be earlier than baseline_start_year.")
    n_years = last_year - first_year + 1
    if min_years < 2:
        raise ValueError("min_baseline_years must be at least 2.")
    if min_years > n_years:
        raise ValueError(
            f"min_baseline_years ({min_years}) exceeds the number of requested baseline "
            f"years ({n_years})."
        )

    lat, lon = check_point_in_nominal_coverage(latitude, longitude)

    years = list(range(first_year, last_year + 1))
    baseline_windows = [
        season_window(YearMonth(year, obs_start.month), window_months_count) for year in years
    ]

    # Fail fast: validate every month of every window BEFORE any download.
    for start, end in [(obs_start, obs_end), *baseline_windows]:
        for month in iter_months(start, end):
            client.store.assert_month_available(month)

    observed_series = client.monthly_point_series(lat, lon, obs_start, obs_end)
    observed_total = accumulated_total_mm(observed_series)
    all_series = [observed_series]

    used: list[YearTotal] = []
    excluded: list[ExcludedYear] = []
    for year, (start, end) in zip(years, baseline_windows, strict=True):
        series = client.monthly_point_series(lat, lon, start, end)
        all_series.append(series)
        try:
            total = accumulated_total_mm(series)
        except MissingDataError:
            missing = [
                f"{v.year:04d}-{v.month:02d}"
                for v in series.values
                if v.precipitation_mm is None
            ]
            excluded.append(
                ExcludedYear(
                    season_year=year,
                    window_start=str(start),
                    window_end=str(end),
                    reason="missing values for: " + ", ".join(missing),
                )
            )
            continue
        used.append(
            YearTotal(
                season_year=year,
                window_start=str(start),
                window_end=str(end),
                total_mm=total,
            )
        )

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
            raise DataIntegrityError(
                "Grid cell differs between windows; refusing to combine them."
            )

    if len(used) < min_years:
        excluded_text = (
            "; ".join(f"{e.season_year} ({e.reason})" for e in excluded) or "none"
        )
        raise InsufficientBaselineError(
            f"Only {len(used)} of {n_years} requested baseline years have complete data "
            f"(minimum required: {min_years}). Excluded years: {excluded_text}."
        )

    baseline_mean = math.fsum(t.total_mm for t in used) / len(used)

    anomaly: float | None
    message: str | None
    try:
        anomaly = percentage_anomaly(observed_total, baseline_mean)
        status: Literal["ok", "undefined"] = "ok"
        message = None
    except AnomalyUndefinedError as exc:
        anomaly = None
        status = "undefined"
        message = str(exc)

    overlaps = any(start <= obs_end and obs_start <= end for start, end in baseline_windows)

    limitations = list(PIPELINE_LIMITATIONS)
    if len(used) < CLIMATOLOGY_REFERENCE_YEARS:
        limitations.append(
            f"The baseline uses only {len(used)} years, shorter than the 30-year length "
            "commonly used for climatologies; the baseline mean is less stable."
        )
    if overlaps:
        limitations.append(
            "The baseline includes the observation window itself, which pulls the baseline "
            "mean toward the observed value and understates the anomaly."
        )
    if excluded:
        limitations.append(
            f"{len(excluded)} baseline year(s) were excluded because of missing values."
        )
    limitations.extend(CHIRPS_V3_LIMITATIONS)

    files: dict[tuple[int, int], SourceFileRecord] = {}
    for series in all_series:
        for prov in series.provenance:
            files[(prov.year, prov.month)] = SourceFileRecord(
                year=prov.year,
                month=prov.month,
                source_url=prov.source_url,
                sha256=prov.sha256,
                size_bytes=prov.size_bytes,
                retrieved_at_utc=prov.retrieved_at_utc,
            )

    first_prov = observed_series.provenance[0]
    return ChirpsRainfallAnomalyResult(
        status=status,
        data_source=DATA_SOURCE,
        percentage_anomaly=anomaly,
        absolute_difference_mm=observed_total - baseline_mean,
        direction=anomaly_direction(observed_total, baseline_mean),
        observed_total_mm=observed_total,
        baseline_mean_mm=baseline_mean,
        formula=FORMULA,
        requested_latitude=lat,
        requested_longitude=lon,
        grid_cell_center_latitude=reference.pixel_center_latitude,
        grid_cell_center_longitude=reference.pixel_center_longitude,
        observed_window_start=str(obs_start),
        observed_window_end=str(obs_end),
        window_months=window_months_count,
        baseline_start_year=first_year,
        baseline_end_year=last_year,
        min_baseline_years=min_years,
        baseline_years_used=len(used),
        baseline_totals=used,
        baseline_excluded=excluded,
        baseline_includes_observed_period=overlaps,
        message=message,
        source_files=[files[key] for key in sorted(files)],
        citation=first_prov.citation,
        doi=first_prov.doi,
        license_note=first_prov.license_note,
        limitations=limitations,
    )