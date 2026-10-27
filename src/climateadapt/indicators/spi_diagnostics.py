"""SPI diagnostics: how much does the gamma assumption matter for one window?

Descriptive only. No pass/fail threshold is defined here.

* ``max_cdf_deviation``: the Kolmogorov-Smirnov D statistic, the largest gap between the
  empirical distribution of the reference window totals and the fitted mixed gamma
  distribution. The mixed distribution has a point mass at 0, so left- and right-hand limits
  are handled separately there.
* ``spi_empirical``: the standard-normal quantile of the empirical mid-rank probability
  (n_below + 0.5 * n_equal) / n of the target among the reference totals. It uses no
  distributional assumption, but it is a crude estimator in the tails (it is undefined when the
  target lies outside the reference range, and ties get half weight).
* ``spi_difference`` = spi_empirical - spi_gamma. A large value means SPI is sensitive to the
  distribution choice.

Reference for the KS statistic: the asymptotic 5% critical value for a FULLY SPECIFIED
distribution is about 1.36 / sqrt(n) (0.25 for n = 30). Parameters estimated from the same
sample make the test more demanding, so a D below that value does not establish a good fit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from scipy.special import ndtri

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    DEFAULT_MIN_REFERENCE_YEARS,
    MIN_NONZERO_VALUES,
    GammaFitError,
    compute_spi,
    cumulative_probability,
    window_sum,
)


@dataclass(frozen=True)
class SpiFitDiagnostics:
    n_reference_years: int
    max_cdf_deviation: float
    gamma_cumulative_probability: float
    empirical_cumulative_probability: float
    spi_gamma: float | None
    spi_empirical: float | None
    spi_difference: float | None


def empirical_cumulative_probability(value: float, reference: Sequence[float]) -> float:
    """Mid-rank empirical probability of ``value`` among ``reference`` values."""
    below = sum(1 for r in reference if r < value)
    equal = sum(1 for r in reference if r == value)
    return (below + 0.5 * equal) / len(reference)


def ks_statistic(
    samples: Sequence[float],
    cdf: Callable[[float], float],
    cdf_left: Callable[[float], float] | None = None,
) -> float:
    """Kolmogorov-Smirnov D between the empirical distribution and ``cdf``.

    ``cdf_left(x)`` is the left-hand limit of the distribution function at ``x``; it defaults to
    ``cdf`` (correct for continuous distributions). A distribution with a point mass needs it.
    """
    ordered = sorted(samples)
    n = len(ordered)
    left = cdf if cdf_left is None else cdf_left
    d = 0.0
    index = 0
    while index < n:
        value = ordered[index]
        end = index
        while end < n and ordered[end] == value:
            end += 1
        # Empirical distribution: left-hand limit index/n, right-hand limit end/n.
        d = max(d, abs(end / n - cdf(value)), abs(index / n - left(value)))
        index = end
    return d


def compute_spi_fit_diagnostics(
    monthly: Mapping[YearMonth, float | None],
    target_end: YearMonth,
    timescale: int,
    reference_start_year: int,
    reference_end_year: int,
    *,
    min_reference_years: int = DEFAULT_MIN_REFERENCE_YEARS,
    min_nonzero_values: int = MIN_NONZERO_VALUES,
) -> SpiFitDiagnostics:
    """Diagnostics for the SPI of the window ending at ``target_end``.

    Uses exactly the reference years and fit of ``compute_spi``; the same errors propagate
    (ValueError, IncompleteWindowError, InsufficientReferenceError), and a degenerate fit
    raises GammaFitError.
    """
    computation = compute_spi(
        monthly,
        target_end,
        timescale,
        reference_start_year,
        reference_end_year,
        min_reference_years=min_reference_years,
        min_nonzero_values=min_nonzero_values,
    )
    fit = computation.fit
    if fit is None:
        raise GammaFitError(computation.reason or "The gamma fit is degenerate.")

    samples: list[float] = []
    for year in computation.reference_years_used:
        total = window_sum(monthly, YearMonth(year, target_end.month), timescale)
        if total is None:  # unreachable: these years were usable in compute_spi
            raise RuntimeError(f"Reference window for {year} unexpectedly incomplete.")
        samples.append(total)

    def cdf(x: float) -> float:
        return cumulative_probability(x, fit)

    def cdf_left(x: float) -> float:
        return 0.0 if x == 0.0 else cdf(x)

    probability = empirical_cumulative_probability(computation.window_total_mm, samples)
    spi_empirical = float(ndtri(probability)) if 0.0 < probability < 1.0 else None
    spi_difference = (
        spi_empirical - computation.spi
        if spi_empirical is not None and computation.spi is not None
        else None
    )
    return SpiFitDiagnostics(
        n_reference_years=len(samples),
        max_cdf_deviation=ks_statistic(samples, cdf, cdf_left),
        gamma_cumulative_probability=cdf(computation.window_total_mm),
        empirical_cumulative_probability=probability,
        spi_gamma=computation.spi,
        spi_empirical=spi_empirical,
        spi_difference=spi_difference,
    )