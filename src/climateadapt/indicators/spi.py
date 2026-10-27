"""Standardized Precipitation Index (SPI): pure, deterministic, tested calculations.

Method (McKee et al. 1993; WMO-No. 1090, 2012)
----------------------------------------------
1. For a target end-month and timescale k, the window total is the sum of the k consecutive
   monthly totals ending in that month.
2. Reference window totals are collected for the SAME calendar end-month in every reference
   year; each calendar month is fitted separately.
3. A two-parameter gamma distribution is fitted to the NON-ZERO reference totals with the
   closed-form Thom (1958) approximation of maximum likelihood:
       A = ln(mean) - mean(ln x),  alpha = (1 + sqrt(1 + 4A/3)) / (4A),  beta = mean / alpha
4. Zeros are a point mass: q = (number of zero totals) / (number of reference totals), and
       H(x) = q + (1 - q) * G(x),  with H(0) = q.
5. SPI = standard-normal quantile of H(x).

Not implemented here, and stated plainly: no goodness-of-fit test, no SPI category labels,
no handling of non-gamma alternatives. SPI describes precipitation relative to the reference
period only; it is not a measure of agricultural drought impact.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Literal

from scipy.special import gammainc, ndtri

from climateadapt.data.periods import YearMonth

MIN_TIMESCALE = 1
MAX_TIMESCALE = 48
DEFAULT_MIN_REFERENCE_YEARS = 30
MIN_REFERENCE_YEARS_FLOOR = 10
MIN_NONZERO_VALUES = 10
_DEGENERATE_A = 1e-12

METHOD = (
    "Gamma distribution (Thom 1958 approximation of maximum likelihood) fitted per calendar "
    "month to non-zero reference window totals; zeros as a point mass q = zeros / reference "
    "years; equiprobability transform to a standard normal quantile (McKee et al. 1993; "
    "WMO-No. 1090)."
)


class InsufficientReferenceError(Exception):
    """Too few usable reference years or non-zero values to fit the distribution."""


class IncompleteWindowError(Exception):
    """The target window has missing months, so no total (and no SPI) can be computed."""


class GammaFitError(Exception):
    """The gamma fit is degenerate (for example, all non-zero totals are identical)."""


@dataclass(frozen=True)
class GammaFit:
    """Fitted mixed distribution for one calendar month."""

    shape: float
    scale: float
    n_total: int
    n_zero: int

    @property
    def n_nonzero(self) -> int:
        return self.n_total - self.n_zero

    @property
    def zero_probability(self) -> float:
        return self.n_zero / self.n_total


@dataclass(frozen=True)
class SpiValue:
    spi: float | None
    cumulative_probability: float
    reason: str | None


@dataclass(frozen=True)
class SpiComputation:
    status: Literal["ok", "undefined"]
    spi: float | None
    cumulative_probability: float | None
    reason: str | None
    window_total_mm: float
    fit: GammaFit | None
    calendar_month: int
    reference_start_year: int
    reference_end_year: int
    reference_years_used: list[int]
    reference_years_unavailable: list[int]
    target_in_reference_period: bool
    reference_spi_mean: float | None
    reference_spi_std: float | None


def _check_total(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number, got {type(value).__name__}.")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative, got {number}.")
    return number


def thom_shape(a: float) -> float:
    """Thom (1958) shape estimate from A = ln(mean) - mean(ln x). Requires A > 0."""
    if isinstance(a, bool) or not isinstance(a, Real) or not math.isfinite(a) or a <= 0:
        raise ValueError(f"A must be a finite positive number, got {a!r}.")
    return (1.0 + math.sqrt(1.0 + 4.0 * a / 3.0)) / (4.0 * a)


def fit_gamma_thom(values: Sequence[float], *, min_nonzero: int = MIN_NONZERO_VALUES) -> GammaFit:
    """Fit the mixed gamma model to reference totals (zeros allowed)."""
    totals = [_check_total("precipitation total", v) for v in values]
    nonzero = [v for v in totals if v > 0.0]
    if len(nonzero) < min_nonzero:
        raise InsufficientReferenceError(
            f"Only {len(nonzero)} non-zero reference totals are available out of "
            f"{len(totals)}; at least {min_nonzero} are needed to fit a gamma distribution."
        )
    mean = math.fsum(nonzero) / len(nonzero)
    mean_log = math.fsum(math.log(v) for v in nonzero) / len(nonzero)
    a = math.log(mean) - mean_log
    if not math.isfinite(a) or a <= _DEGENERATE_A:
        raise GammaFitError(
            "The non-zero reference totals are (almost) identical, so a gamma distribution "
            "cannot be fitted."
        )
    shape = thom_shape(a)
    return GammaFit(
        shape=shape,
        scale=mean / shape,
        n_total=len(totals),
        n_zero=len(totals) - len(nonzero),
    )


def cumulative_probability(x: float, fit: GammaFit) -> float:
    """H(x) = q + (1 - q) * G(x); H(0) = q."""
    total = _check_total("precipitation total", x)
    q = fit.zero_probability
    if total == 0.0:
        return q
    return q + (1.0 - q) * float(gammainc(fit.shape, total / fit.scale))


def spi_from_fit(x: float, fit: GammaFit) -> SpiValue:
    """Map a window total to SPI. SPI is None when H is not strictly inside (0, 1)."""
    probability = cumulative_probability(x, fit)
    if not 0.0 < probability < 1.0:
        return SpiValue(
            spi=None,
            cumulative_probability=probability,
            reason=(
                f"The cumulative probability is {probability}, outside (0, 1), so the "
                "standard-normal quantile is infinite and SPI is undefined."
            ),
        )
    return SpiValue(spi=float(ndtri(probability)), cumulative_probability=probability, reason=None)


def window_months(end: YearMonth, timescale: int) -> list[YearMonth]:
    """The ``timescale`` consecutive months ending at ``end`` (ascending)."""
    index = end.year * 12 + (end.month - 1)
    months: list[YearMonth] = []
    for offset in range(timescale - 1, -1, -1):
        year, month0 = divmod(index - offset, 12)
        months.append(YearMonth(year, month0 + 1))
    return months


def window_sum(
    monthly: Mapping[YearMonth, float | None],
    end: YearMonth,
    timescale: int,
) -> float | None:
    """Sum of the window ending at ``end``; None if any month is absent or missing."""
    try:
        months = window_months(end, timescale)
    except ValueError:
        return None
    values = [monthly.get(m) for m in months]
    if any(v is None for v in values):
        return None
    return math.fsum(v for v in values if v is not None)


def validate_parameters(
    timescale: object,
    reference_start_year: object,
    reference_end_year: object,
    min_reference_years: object,
) -> None:
    """Validate SPI parameters (raises ValueError)."""
    for name, value in (
        ("timescale", timescale),
        ("reference_start_year", reference_start_year),
        ("reference_end_year", reference_end_year),
        ("min_reference_years", min_reference_years),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer, got {value!r}.")
    assert isinstance(timescale, int) and isinstance(min_reference_years, int)
    assert isinstance(reference_start_year, int) and isinstance(reference_end_year, int)
    if not MIN_TIMESCALE <= timescale <= MAX_TIMESCALE:
        raise ValueError(
            f"timescale must be between {MIN_TIMESCALE} and "
            f"{MAX_TIMESCALE} months, got {timescale}."
        )
    if reference_end_year < reference_start_year:
        raise ValueError("reference_end_year must not be earlier than reference_start_year.")
    if min_reference_years < MIN_REFERENCE_YEARS_FLOOR:
        raise ValueError(
            f"min_reference_years must be at least {MIN_REFERENCE_YEARS_FLOOR}, "
            f"got {min_reference_years}."
        )
    n_years = reference_end_year - reference_start_year + 1
    if min_reference_years > n_years:
        raise ValueError(
            f"min_reference_years ({min_reference_years}) exceeds the number of reference "
            f"years ({n_years})."
        )


def compute_spi(
    monthly: Mapping[YearMonth, float | None],
    target_end: YearMonth,
    timescale: int,
    reference_start_year: int,
    reference_end_year: int,
    *,
    min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
    min_nonzero_values: int = MIN_NONZERO_VALUES,
) -> SpiComputation:
    """Compute SPI for the window ending at ``target_end`` from monthly totals (mm).

    Raises:
        ValueError: invalid parameters or invalid monthly values.
        IncompleteWindowError: the target window has a missing month.
        InsufficientReferenceError: too few usable reference years or non-zero values.
    """
    validate_parameters(timescale, reference_start_year, reference_end_year, min_reference_years)
    for month, value in monthly.items():
        if value is not None:
            _check_total(f"monthly total for {month}", value)

    total = window_sum(monthly, target_end, timescale)
    if total is None:
        missing = [
            str(m) for m in window_months(target_end, timescale) if monthly.get(m) is None
        ]
        raise IncompleteWindowError(
            "The target window has no value for: " + ", ".join(missing) + ". SPI cannot be "
            "computed from an incomplete window."
        )

    samples: list[float] = []
    used: list[int] = []
    unavailable: list[int] = []
    for year in range(reference_start_year, reference_end_year + 1):
        reference_total = window_sum(monthly, YearMonth(year, target_end.month), timescale)
        if reference_total is None:
            unavailable.append(year)
        else:
            samples.append(reference_total)
            used.append(year)

    n_years = reference_end_year - reference_start_year + 1
    if len(samples) < min_reference_years:
        listed = (
            ", ".join(str(y) for y in unavailable[:10])
            + (" ..." if len(unavailable) > 10 else "")
        )
        raise InsufficientReferenceError(
            f"Only {len(samples)} of {n_years} reference years have a complete {timescale}-month "
            f"window ending in calendar month {target_end.month} (minimum required: "
            f"{min_reference_years}). Unavailable years: {listed or 'none'}."
        )

    common = {
        "window_total_mm": total,
        "calendar_month": target_end.month,
        "reference_start_year": reference_start_year,
        "reference_end_year": reference_end_year,
        "reference_years_used": used,
        "reference_years_unavailable": unavailable,
        "target_in_reference_period": reference_start_year <= target_end.year <= reference_end_year,
    }

    try:
        fit = fit_gamma_thom(samples, min_nonzero=min_nonzero_values)
    except GammaFitError as exc:
        return SpiComputation(
            status="undefined",
            spi=None,
            cumulative_probability=None,
            reason=str(exc),
            fit=None,
            reference_spi_mean=None,
            reference_spi_std=None,
            **common,
        )

    value = spi_from_fit(total, fit)
    reference_spi = [
        z for z in (spi_from_fit(x, fit).spi for x in samples) if z is not None
    ]
    return SpiComputation(
        status="ok" if value.spi is not None else "undefined",
        spi=value.spi,
        cumulative_probability=value.cumulative_probability,
        reason=value.reason,
        fit=fit,
        reference_spi_mean=statistics.fmean(reference_spi) if reference_spi else None,
        reference_spi_std=statistics.stdev(reference_spi) if len(reference_spi) >= 2 else None,
        **common,
    )