"""Generic day-weighted window anomaly: pure, deterministic calculation core.

Shared by the temperature (degC differences) and soil-moisture (m3/m3) indicators.
Validity checks are supplied by the caller (plausible ranges differ by variable);
the statistics are identical for both:

* Window mean: the DAY-WEIGHTED mean of the monthly values of ``timescale``
  consecutive months (each month weighted by its number of days).
* Reference: the same window ending in the same calendar month in each reference year.
* anomaly = target window mean - mean of the reference window means (a DIFFERENCE
  in the variable's units, not a percentage).
* standardized_anomaly = anomaly / sample standard deviation (ddof=1) of the reference
  means. It assumes nothing about normality and is itself uncertain with ~30 values.
* percentile_rank = (n_below + 0.5 * n_equal) / n of the reference means (empirical
  mid-rank).

Reference years whose window is incomplete are excluded and reported, never imputed.
Callers state their own limitations (trends, timing, interpretation) in their own
modules and pipeline limitation lists.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    DEFAULT_MIN_REFERENCE_YEARS,
    IncompleteWindowError,
    InsufficientReferenceError,
    validate_parameters,
    window_months,
)
from climateadapt.indicators.units import days_in_month


@dataclass(frozen=True)
class WindowAnomaly:
    window_mean: float
    reference_mean: float
    anomaly: float
    reference_sd: float | None
    standardized_anomaly: float | None
    percentile_rank: float
    reason: str | None
    calendar_month: int
    reference_start_year: int
    reference_end_year: int
    reference_years_used: list[int]
    reference_years_unavailable: list[int]
    target_in_reference_period: bool


def window_day_weighted_mean(
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


def mid_rank_percentile(value: float, reference: Sequence[float]) -> float:
    """Empirical mid-rank percentile (0-1) of ``value`` within ``reference``."""
    below = sum(1 for r in reference if r < value)
    equal = sum(1 for r in reference if r == value)
    return (below + 0.5 * equal) / len(reference)


def compute_window_anomaly(
    monthly: Mapping[YearMonth, float | None],
    target_end: YearMonth,
    timescale: int,
    reference_start_year: int,
    reference_end_year: int,
    *,
    min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
    check_value: Callable[[YearMonth, object], float] | None = None,
    sd_floor: float = 1e-9,
) -> WindowAnomaly:
    """Window anomaly of the window ending at ``target_end`` (monthly means).

    ``check_value`` validates each present monthly value (raising ValueError); it is
    supplied by the caller because plausible ranges are unit-specific. ``sd_floor`` is
    the absolute spread below which the standardized anomaly is left undefined.

    Raises:
        ValueError: invalid parameters or implausible values.
        IncompleteWindowError: the target window has a missing month.
        InsufficientReferenceError: too few usable reference years.
    """
    validate_parameters(timescale, reference_start_year, reference_end_year, min_reference_years)
    if check_value is not None:
        for month, value in monthly.items():
            if value is not None:
                check_value(month, value)

    target = window_day_weighted_mean(monthly, target_end, timescale)
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
        mean = window_day_weighted_mean(monthly, YearMonth(year, target_end.month), timescale)
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
    if sd > sd_floor:
        standardized: float | None = anomaly / sd
        reason = None
    else:
        standardized = None
        reason = (
            "The reference window means are (almost) identical, so the standardized anomaly "
            "is undefined."
        )

    return WindowAnomaly(
        window_mean=target,
        reference_mean=reference_mean,
        anomaly=anomaly,
        reference_sd=sd,
        standardized_anomaly=standardized,
        percentile_rank=mid_rank_percentile(target, samples),
        reason=reason,
        calendar_month=target_end.month,
        reference_start_year=reference_start_year,
        reference_end_year=reference_end_year,
        reference_years_used=used,
        reference_years_unavailable=unavailable,
        target_in_reference_period=reference_start_year <= target_end.year <= reference_end_year,
    )
