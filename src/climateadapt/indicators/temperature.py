"""Temperature window anomaly: pure, deterministic, tested calculations.

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
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    DEFAULT_MIN_REFERENCE_YEARS,
    IncompleteWindowError,
    InsufficientReferenceError,
    validate_parameters,
    window_months,
)
from climateadapt.indicators.units import days_in_month

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
    try:
        months = window_months(end, timescale)
    except ValueError:
        return None
    values = [monthly.get(m) for m in months]
    if any(v is None for v in values):
        return None
    weights = [days_in_month(m.year, m.month) for m in months]
    weighted = math.fsum(v * w for v, w in zip(values, weights, strict=True) if v is not None)
    return weighted / sum(weights)


def percentile_rank(value: float, reference: Sequence[float]) -> float:
    """Empirical mid-rank percentile (0-1) of ``value`` within ``reference``."""
    below = sum(1 for r in reference if r < value)
    equal = sum(1 for r in reference if r == value)
    return (below + 0.5 * equal) / len(reference)


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
    validate_parameters(timescale, reference_start_year, reference_end_year, min_reference_years)
    for month, value in monthly.items():
        if value is not None:
            _check_temperature(f"temperature for {month}", value)

    target = window_mean_c(monthly, target_end, timescale)
    if target is None:
        missing = [str(m) for m in window_months(target_end, timescale) if monthly.get(m) is None]
        raise IncompleteWindowError(
            "The target window has no value for: " + ", ".join(missing) + ". The anomaly "
            "cannot be computed from an incomplete window."
        )

    samples: list[float] = []
    used: list[int] = []
    unavailable: list[int] = []
    for year in range(reference_start_year, reference_end_year + 1):
        mean = window_mean_c(monthly, YearMonth(year, target_end.month), timescale)
        if mean is None:
            unavailable.append(year)
        else:
            samples.append(mean)
            used.append(year)

    n_years = reference_end_year - reference_start_year + 1
    if len(samples) < min_reference_years:
        listed = ", ".join(str(y) for y in unavailable[:10]) + (
            " ..." if len(unavailable) > 10 else ""
        )
        raise InsufficientReferenceError(
            f"Only {len(samples)} of {n_years} reference years have a complete {timescale}-month "
            f"window ending in calendar month {target_end.month} (minimum required: "
            f"{min_reference_years}). Unavailable years: {listed or 'none'}."
        )

    reference_mean = statistics.fmean(samples)
    sd = statistics.stdev(samples)
    anomaly = target - reference_mean
    if sd > _MIN_SD_C:
        standardized: float | None = anomaly / sd
        reason = None
    else:
        standardized = None
        reason = (
            "The reference window means are (almost) identical, so the standardized anomaly "
            "is undefined."
        )

    return TemperatureAnomaly(
        window_mean_c=target,
        reference_mean_c=reference_mean,
        anomaly_c=anomaly,
        reference_sd_c=sd,
        standardized_anomaly=standardized,
        percentile_rank=percentile_rank(target, samples),
        reason=reason,
        calendar_month=target_end.month,
        reference_start_year=reference_start_year,
        reference_end_year=reference_end_year,
        reference_years_used=used,
        reference_years_unavailable=unavailable,
        target_in_reference_period=reference_start_year <= target_end.year <= reference_end_year,
    )