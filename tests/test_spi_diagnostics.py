import numpy as np
import pytest
from scipy import stats

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    GammaFitError,
    InsufficientReferenceError,
    compute_spi,
    cumulative_probability,
    fit_gamma_thom,
)
from climateadapt.indicators.spi_diagnostics import (
    compute_spi_fit_diagnostics,
    empirical_cumulative_probability,
    ks_statistic,
)


def make_monthly(first_year=1990, last_year=2024, seed=1, zeros=frozenset(), constant=None):
    rng = np.random.default_rng(seed)
    monthly = {}
    for year in range(first_year, last_year + 1):
        for month in range(1, 13):
            value = float(rng.gamma(2.5, 12.0))
            if constant is not None and month == constant[0]:
                value = constant[1]
            if (year, month) in zeros:
                value = 0.0
            monthly[YearMonth(year, month)] = value
    return monthly


def test_ks_statistic_hand_checkable():
    # Uniform on [0, 4]: every step of the empirical distribution is 0.25 away from F.
    assert ks_statistic([1.0, 2.0, 3.0, 4.0], lambda x: x / 4.0) == pytest.approx(0.25)


def test_ks_statistic_matches_scipy_for_a_continuous_fit():
    sample = np.random.default_rng(7).gamma(2.5, 30.0, size=200).tolist()
    fit = fit_gamma_thom(sample)

    def cdf(x):
        return float(stats.gamma.cdf(x, a=fit.shape, scale=fit.scale))

    assert ks_statistic(sample, cdf) == pytest.approx(
        stats.kstest(sample, cdf).statistic, 
        abs=1e-12
    )


def test_ks_statistic_handles_the_point_mass_at_zero():
    rng = np.random.default_rng(3)
    sample = [0.0] * 8 + rng.gamma(2.0, 20.0, size=32).tolist()  # q = 0.2
    fit = fit_gamma_thom(sample)

    def cdf(x):
        return cumulative_probability(x, fit)

    def cdf_left(x):
        return 0.0 if x == 0.0 else cdf(x)

    ours = ks_statistic(sample, cdf, cdf_left)

    # Independent check: dense evaluation including both sides of every data point.
    data = np.sort(np.array(sample))
    unique = np.unique(data)
    grid = np.concatenate([unique, unique - 1e-9, np.linspace(-1.0, data.max() + 1.0, 20001)])
    ecdf = np.searchsorted(data, grid, side="right") / data.size
    q = fit.zero_probability
    mixed = np.where(
        grid < 0,
        0.0,
        q + (1 - q) * stats.gamma.cdf(np.maximum(grid, 0.0), a=fit.shape, scale=fit.scale),
    )
    assert ours == pytest.approx(float(np.max(np.abs(ecdf - mixed))), abs=1e-6)


def test_empirical_probability_is_a_mid_rank():
    assert empirical_cumulative_probability(5.0, [1.0, 2.0, 3.0, 4.0]) == 1.0
    assert empirical_cumulative_probability(0.0, [1.0, 2.0, 3.0, 4.0]) == 0.0
    assert empirical_cumulative_probability(2.0, [1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.5 / 4)


def test_diagnostics_are_consistent_with_compute_spi_and_scipy():
    monthly = make_monthly()
    target = YearMonth(2024, 6)

    diag = compute_spi_fit_diagnostics(monthly, target, 1, 1991, 2020)
    computation = compute_spi(monthly, target, 1, 1991, 2020)

    june = [monthly[YearMonth(y, 6)] for y in range(1991, 2021)]
    below = sum(1 for v in june if v < monthly[target])
    p_empirical = below / 30  # no ties in continuous data
    fit = computation.fit

    assert diag.n_reference_years == 30
    assert diag.spi_gamma == pytest.approx(computation.spi)
    assert diag.gamma_cumulative_probability == pytest.approx(computation.cumulative_probability)
    assert diag.empirical_cumulative_probability == pytest.approx(p_empirical)
    assert diag.spi_empirical == pytest.approx(stats.norm.ppf(p_empirical), abs=1e-9)
    assert diag.spi_difference == pytest.approx(diag.spi_empirical - diag.spi_gamma)
    expected_d = stats.kstest(
        june, lambda x: stats.gamma.cdf(x, a=fit.shape, scale=fit.scale)
    ).statistic
    assert diag.max_cdf_deviation == pytest.approx(expected_d, abs=1e-12)
    assert 0.0 <= diag.max_cdf_deviation <= 1.0


def test_target_beyond_the_reference_range_has_no_empirical_spi():
    monthly = make_monthly()
    monthly[YearMonth(2024, 6)] = 1e6

    diag = compute_spi_fit_diagnostics(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert diag.empirical_cumulative_probability == 1.0
    assert diag.spi_empirical is None
    assert diag.spi_difference is None


def test_zero_totals_use_the_mid_rank_convention_for_ties():
    zeros = {(y, 8) for y in (1995, 1998, 2001, 2004, 2007, 2010)} | {(2024, 8)}
    diag = compute_spi_fit_diagnostics(
        make_monthly(zeros=zeros), YearMonth(2024, 8), 1, 1991, 2020
    )

    assert diag.gamma_cumulative_probability == pytest.approx(0.2)  # q = 6/30
    assert diag.empirical_cumulative_probability == pytest.approx(0.1)  # 6 ties, half weight
    assert diag.spi_gamma == pytest.approx(stats.norm.ppf(0.2))
    assert diag.spi_empirical == pytest.approx(stats.norm.ppf(0.1))
    assert diag.max_cdf_deviation == pytest.approx(
        diag.max_cdf_deviation
    )  # finite and defined with a point mass


def test_errors_propagate_from_the_spi_calculation():
    monthly = make_monthly()
    with pytest.raises(ValueError):
        compute_spi_fit_diagnostics(monthly, YearMonth(2024, 6), 0, 1991, 2020)

    monthly[YearMonth(1995, 6)] = None
    with pytest.raises(InsufficientReferenceError, match="Only 29 of 30"):
        compute_spi_fit_diagnostics(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    constant = make_monthly(constant=(6, 50.0))
    with pytest.raises(GammaFitError, match="identical"):
        compute_spi_fit_diagnostics(constant, YearMonth(2024, 6), 1, 1991, 2020)