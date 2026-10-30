"""Soil-moisture window anomaly: pure, deterministic, tested calculations.

Thin wrapper over :mod:`climateadapt.indicators.window_anomaly`: the statistics live in
the shared core; this module supplies the soil-water plausibility check ([0, 1] m3/m3)
and the soil-specific result type.

Definitions
-----------
* Window mean: the DAY-WEIGHTED mean of the monthly mean volumetric soil water (m3/m3)
  of ``timescale`` consecutive months (each month weighted by its number of days).
* Reference: the same window ending in the same calendar month in each reference year.
* anomaly = target window mean - mean of the reference window means (a DIFFERENCE in
  m3/m3, not a percentage).
* standardized_anomaly = anomaly / sample standard deviation (ddof=1) of the reference
  means. It assumes nothing about normality and is itself uncertain with ~30 values.
* percentile_rank = (n_below + 0.5 * n_equal) / n of the reference means (empirical
  mid-rank).

Only anomalies are meaningful output: absolute ERA5-Land soil water can be biased, so
pipelines must report the anomaly (and its spread), never bare absolute values as truth.
Monthly means cannot show the timing of wetting or drying within the window.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Real

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import DEFAULT_MIN_REFERENCE_YEARS
from climateadapt.indicators.window_anomaly import compute_window_anomaly

MIN_PLAUSIBLE_M3M3 = 0.0
MAX_PLAUSIBLE_M3M3 = 1.0
_MIN_SD_M3M3 = 1e-9


@dataclass(frozen=True)
class SoilMoistureAnomaly:
    window_mean_m3m3: float
    reference_mean_m3m3: float
    anomaly_m3m3: float
    reference_sd_m3m3: float | None
    standardized_anomaly: float | None
    percentile_rank: float
    reason: str | None
    calendar_month: int
    reference_start_year: int
    reference_end_year: int
    reference_years_used: list[int]
    reference_years_unavailable: list[int]
    target_in_reference_period: bool


def _check_soil_water(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in m3/m3, got {type(value).__name__}.")
    number = float(value)
    if not math.isfinite(number) or not MIN_PLAUSIBLE_M3M3 <= number <= MAX_PLAUSIBLE_M3M3:
        raise ValueError(
            f"{name} must be a finite volumetric soil water between {MIN_PLAUSIBLE_M3M3:g} "
            f"and {MAX_PLAUSIBLE_M3M3:g} m3/m3, got {number}."
        )
    return number


def compute_soil_moisture_anomaly(
    monthly: Mapping[YearMonth, float | None],
    target_end: YearMonth,
    timescale: int,
    reference_start_year: int,
    reference_end_year: int,
    *,
    min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
) -> SoilMoistureAnomaly:
    """Soil-moisture anomaly of the window ending at ``target_end`` (m3/m3).

    Raises:
        ValueError: invalid parameters or implausible soil-water values.
        IncompleteWindowError: the target window has a missing month.
        InsufficientReferenceError: too few usable reference years.
    """
    core = compute_window_anomaly(
        monthly,
        target_end,
        timescale,
        reference_start_year,
        reference_end_year,
        min_reference_years=min_reference_years,
        check_value=lambda month, value: _check_soil_water(
            f"soil water for {month}", value
        ),
        sd_floor=_MIN_SD_M3M3,
    )
    return SoilMoistureAnomaly(
        window_mean_m3m3=core.window_mean,
        reference_mean_m3m3=core.reference_mean,
        anomaly_m3m3=core.anomaly,
        reference_sd_m3m3=core.reference_sd,
        standardized_anomaly=core.standardized_anomaly,
        percentile_rank=core.percentile_rank,
        reason=core.reason,
        calendar_month=core.calendar_month,
        reference_start_year=core.reference_start_year,
        reference_end_year=core.reference_end_year,
        reference_years_used=core.reference_years_used,
        reference_years_unavailable=core.reference_years_unavailable,
        target_in_reference_period=core.target_in_reference_period,
    )
