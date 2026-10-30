"""Temperature window anomaly: pure, deterministic, tested calculations.

Thin wrapper over :mod:`climateadapt.indicators.window_anomaly` (P04): the statistics
live in the shared core; this module keeps the temperature public API, field names,
units, plausibility checks, and results identical.

Definitions
-----------
* Window mean: the DAY-WEIGHTED mean of the monthly mean temperatures (degC) of ``timescale``
  consecutive months (each month weighted by its number of days).
* Reference: the same window ending in the same calendar month in each reference year.
* anomaly_c = target window mean - mean of the reference window means (a DIFFERENCE in degC,
  not a percentage).
* standardized_anomaly = anomaly / sample standard deviation (ddof=1) of the reference means.
  It assumes nothing about normality and is itself uncertain with ~30 values.
* percentile_rank = (n_below + 0.5 * n_equal) / n of the reference means (empirical mid-rank).

Not handled, and stated plainly: the reference mean includes any warming trend inside the
reference period (no detrending); monthly means cannot show heat waves, frost, or timing.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import DEFAULT_MIN_REFERENCE_YEARS
from climateadapt.indicators.window_anomaly import (
    compute_window_anomaly,
    mid_rank_percentile,
    window_day_weighted_mean,
)

MIN_PLAUSIBLE_C = -100.0
MAX_PLAUSIBLE_C = 60.0
_MIN_SD_C = 1e-9


@dataclass(frozen=True)
class TemperatureAnomaly:
    window_mean_c: float
    reference_mean_c: float
    anomaly_c: float
    reference_sd_c: float | None
    standardized_anomaly: float | None
    percentile_rank: float
    reason: str | None
    calendar_month: int
    reference_start_year: int
    reference_end_year: int
    reference_years_used: list[int]
    reference_years_unavailable: list[int]
    target_in_reference_period: bool


def _check_temperature(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in degC, got {type(value).__name__}.")
    number = float(value)
    if not math.isfinite(number) or not MIN_PLAUSIBLE_C <= number <= MAX_PLAUSIBLE_C:
        raise ValueError(
            f"{name} must be a finite temperature between {MIN_PLAUSIBLE_C:g} and "
            f"{MAX_PLAUSIBLE_C:g} degC, got {number} (is it in kelvin by mistake?)."
        )
    return number


def window_mean_c(
    monthly: Mapping[YearMonth, float | None], end: YearMonth, timescale: int
) -> float | None:
    """Day-weighted mean of the window ending at ``end``; None if any month is missing."""
    return window_day_weighted_mean(monthly, end, timescale)


def percentile_rank(value: float, reference: Sequence[float]) -> float:
    """Empirical mid-rank percentile (0-1) of ``value`` within ``reference``."""
    return mid_rank_percentile(value, reference)


def compute_temperature_anomaly(
    monthly: Mapping[YearMonth, float | None],
    target_end: YearMonth,
    timescale: int,
    reference_start_year: int,
    reference_end_year: int,
    *,
    min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
) -> TemperatureAnomaly:
    """Temperature anomaly of the window ending at ``target_end`` (monthly means in degC).

    Raises:
        ValueError: invalid parameters or implausible temperatures.
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
        check_value=lambda month, value: _check_temperature(f"temperature for {month}", value),
        sd_floor=_MIN_SD_C,
    )
    return TemperatureAnomaly(
        window_mean_c=core.window_mean,
        reference_mean_c=core.reference_mean,
        anomaly_c=core.anomaly,
        reference_sd_c=core.reference_sd,
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
