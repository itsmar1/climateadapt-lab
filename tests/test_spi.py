import math

import numpy as np
import pytest
from scipy import stats

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    GammaFit,
    GammaFitError,
    IncompleteWindowError,
    InsufficientReferenceError,
    compute_spi,
    cumulative_probability,
    fit_gamma_thom,
    spi_from_fit,
    thom_shape,
    window_months,
    window_sum,
)

EULER_GAMMA = 0.5772157


def gamma_sample(n, shape=2.5, scale=30.0, seed=42):
    return np.random.default_rng(seed).gamma(shape, scale, size=n).tolist()


def make_monthly(first_year=1990, last_year=2024, seed=1, zeros=frozenset(), constant=None):
    """Synthetic monthly totals (mm). ``constant`` = (month, value) fixes that month."""
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


# ---------------------------------------------------------------- Thom approximation


def test_thom_shape_reference_value():
    # For an exponential distribution E[ln x] = ln(scale) - 0.5772, so A ~ 0.5772 and the
    # Thom estimate is (1 + sqrt(1 + 4A/3)) / (4A) = 1.00927 (hand calculation).
    assert thom_shape(EULER_GAMMA) == pytest.approx(1.00927, rel=5e-4)


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf, True, "1"])
def test_thom_shape_rejects_invalid(bad):
    with pytest.raises(ValueError):
        thom_shape(bad)


def test_fit_matches_scipy_maximum_likelihood_and_the_true_parameters():
    data = gamma_sample(5000)
    fit = fit_gamma_thom(data)
    shape_mle, _, scale_mle = stats.gamma.fit(data, floc=0)

    assert fit.shape == pytest.approx(shape_mle, rel=0.02)
    assert fit.scale == pytest.approx(scale_mle, rel=0.02)
    assert fit.shape == pytest.approx(2.5, rel=0.08)
    assert fit.scale == pytest.approx(30.0, rel=0.08)
    assert (fit.n_total, fit.n_zero, fit.n_nonzero) == (5000, 0, 5000)
    assert fit.zero_probability == 0.0


def test_zeros_are_excluded_from_the_fit_and_counted_in_q():
    nonzero = gamma_sample(80)
    with_zeros = fit_gamma_thom(nonzero + [0.0] * 20)
    without = fit_gamma_thom(nonzero)

    assert with_zeros.shape == pytest.approx(without.shape, rel=1e-12)
    assert with_zeros.scale == pytest.approx(without.scale, rel=1e-12)
    assert (with_zeros.n_total, with_zeros.n_zero) == (100, 20)
    assert with_zeros.zero_probability == pytest.approx(0.2)


def test_too_few_nonzero_values_is_insufficient_but_ten_is_enough():
    with pytest.raises(InsufficientReferenceError, match="at least 10"):
        fit_gamma_thom([0.0] * 25 + gamma_sample(9))
    assert fit_gamma_thom([0.0] * 25 + gamma_sample(10)).n_nonzero == 10


def test_identical_nonzero_values_are_a_degenerate_fit():
    with pytest.raises(GammaFitError, match="identical"):
        fit_gamma_thom([5.0] * 30)


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf, True, "5", None])
def test_fit_rejects_invalid_values(bad):
    with pytest.raises(ValueError):
        fit_gamma_thom([*gamma_sample(20), bad])


# ---------------------------------------------------------------- probability and SPI


def test_zero_total_has_probability_q_and_spi_ndtri_q():
    fit = fit_gamma_thom(gamma_sample(80) + [0.0] * 20)  # q = 0.2
    assert cumulative_probability(0.0, fit) == pytest.approx(0.2)
    assert spi_from_fit(0.0, fit).spi == pytest.approx(stats.norm.ppf(0.2), abs=1e-9)
    assert stats.norm.ppf(0.2) == pytest.approx(-0.8416212, abs=1e-6)


@pytest.mark.parametrize("p", [0.025, 0.1, 0.5, 0.9, 0.975])
def test_spi_at_fitted_quantiles_equals_normal_quantiles(p):
    fit = fit_gamma_thom(gamma_sample(200))
    x = stats.gamma.ppf(p, a=fit.shape, scale=fit.scale)
    assert spi_from_fit(float(x), fit).spi == pytest.approx(stats.norm.ppf(p), abs=1e-6)


@pytest.mark.parametrize("p", [0.4, 0.5, 0.9, 0.975])
def test_spi_with_zero_mass_uses_the_mixed_distribution(p):
    fit = fit_gamma_thom(gamma_sample(80) + [0.0] * 20)  # q = 0.2
    q = fit.zero_probability
    x = stats.gamma.ppf((p - q) / (1 - q), a=fit.shape, scale=fit.scale)
    assert spi_from_fit(float(x), fit).spi == pytest.approx(stats.norm.ppf(p), abs=1e-6)


def test_spi_increases_with_the_total():
    fit = fit_gamma_thom(gamma_sample(60))
    values = [spi_from_fit(x, fit).spi for x in (1.0, 20.0, 60.0, 120.0, 250.0)]
    assert values == sorted(values)
    assert len(set(values)) == 5


def test_calibration_sample_is_standardised():
    data = gamma_sample(3000)
    fit = fit_gamma_thom(data)
    z = [spi_from_fit(x, fit).spi for x in data]
    assert abs(np.mean(z)) < 0.07
    assert np.std(z, ddof=1) == pytest.approx(1.0, abs=0.07)


def test_probability_of_exactly_one_gives_undefined_spi():
    fit = GammaFit(shape=2.0, scale=1.0, n_total=30, n_zero=0)
    value = spi_from_fit(1e6, fit)
    assert value.spi is None
    assert value.cumulative_probability == 1.0
    assert "outside (0, 1)" in value.reason


def test_zero_total_with_no_zero_mass_gives_undefined_spi():
    fit = GammaFit(shape=2.0, scale=1.0, n_total=30, n_zero=0)
    value = spi_from_fit(0.0, fit)
    assert value.spi is None
    assert value.cumulative_probability == 0.0


# ---------------------------------------------------------------- windows


def test_window_months_cross_the_year_boundary():
    months = window_months(YearMonth(2021, 2), 4)
    assert [str(m) for m in months] == ["2020-11", "2020-12", "2021-01", "2021-02"]


def test_window_sum_requires_every_month():
    monthly = {YearMonth(2020, m): float(m) for m in range(1, 7)}
    assert window_sum(monthly, YearMonth(2020, 4), 3) == pytest.approx(9.0)  # 2+3+4
    assert window_sum(monthly, YearMonth(2020, 2), 3) is None  # needs 2019-12
    monthly[YearMonth(2020, 3)] = None
    assert window_sum(monthly, YearMonth(2020, 4), 3) is None


# ---------------------------------------------------------------- compute_spi


def test_single_month_spi_is_consistent_with_its_own_fit():
    monthly = make_monthly()
    result = compute_spi(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert result.status == "ok"
    assert result.reference_years_used == list(range(1991, 2021))
    assert result.reference_years_unavailable == []
    assert result.target_in_reference_period is False
    assert result.calendar_month == 6
    assert result.window_total_mm == pytest.approx(monthly[YearMonth(2024, 6)])
    fit = result.fit
    assert stats.norm.cdf(result.spi) == pytest.approx(result.cumulative_probability, abs=1e-9)
    assert result.cumulative_probability == pytest.approx(
        stats.gamma.cdf(result.window_total_mm, a=fit.shape, scale=fit.scale), abs=1e-9
    )
    june = [monthly[YearMonth(y, 6)] for y in range(1991, 2021)]
    assert fit.shape == pytest.approx(stats.gamma.fit(june, floc=0)[0], rel=0.03)
    assert math.isfinite(result.reference_spi_mean)
    assert result.reference_spi_std > 0


def test_three_month_windows_are_assembled_from_the_right_months():
    monthly = make_monthly()
    result = compute_spi(monthly, YearMonth(2024, 3), 3, 1991, 2020)

    sums = [
        monthly[YearMonth(y, 1)] + monthly[YearMonth(y, 2)] + monthly[YearMonth(y, 3)]
        for y in range(1991, 2021)
    ]
    expected_fit = fit_gamma_thom(sums)
    assert result.fit.shape == pytest.approx(expected_fit.shape, rel=1e-9)
    assert result.fit.scale == pytest.approx(expected_fit.scale, rel=1e-9)
    expected_total = sum(monthly[YearMonth(2024, m)] for m in (1, 2, 3))
    assert result.window_total_mm == pytest.approx(expected_total)


def test_windows_crossing_a_year_boundary_use_the_previous_december():
    monthly = make_monthly(first_year=1990)
    result = compute_spi(monthly, YearMonth(2024, 2), 3, 1991, 2020)

    sums = [
        monthly[YearMonth(y - 1, 12)] + monthly[YearMonth(y, 1)] + monthly[YearMonth(y, 2)]
        for y in range(1991, 2021)
    ]
    assert result.fit.shape == pytest.approx(fit_gamma_thom(sums).shape, rel=1e-9)
    expected_total = (
        monthly[YearMonth(2023, 12)] + monthly[YearMonth(2024, 1)] + monthly[YearMonth(2024, 2)]
    )
    assert result.window_total_mm == pytest.approx(expected_total)


def test_reference_years_without_a_complete_window_are_excluded_not_imputed():
    monthly = make_monthly(first_year=1991)  # no December 1990
    with pytest.raises(InsufficientReferenceError, match="Only 29 of 30"):
        compute_spi(monthly, YearMonth(2024, 2), 3, 1991, 2020)

    result = compute_spi(monthly, YearMonth(2024, 2), 3, 1991, 2020, min_reference_years=20)
    assert result.reference_years_unavailable == [1991]
    assert result.reference_years_used == list(range(1992, 2021))


def test_a_missing_month_excludes_only_that_reference_year():
    monthly = make_monthly()
    monthly[YearMonth(1995, 3)] = None
    result = compute_spi(monthly, YearMonth(2024, 3), 3, 1991, 2020, min_reference_years=20)
    assert result.reference_years_unavailable == [1995]
    assert len(result.reference_years_used) == 29


def test_incomplete_target_window_raises():
    monthly = make_monthly()
    monthly[YearMonth(2024, 2)] = None
    with pytest.raises(IncompleteWindowError, match="2024-02"):
        compute_spi(monthly, YearMonth(2024, 3), 3, 1991, 2020)


def test_target_inside_the_reference_period_is_flagged():
    monthly = make_monthly()
    assert compute_spi(monthly, YearMonth(2020, 6), 1, 1991, 2020).target_in_reference_period
    assert not compute_spi(monthly, YearMonth(2024, 6), 1, 1991, 2020).target_in_reference_period


def test_zero_rainfall_month_maps_to_the_quantile_of_q():
    zeros = {(y, 8) for y in (1995, 1998, 2001, 2004, 2007, 2010)} | {(2024, 8)}
    result = compute_spi(make_monthly(zeros=zeros), YearMonth(2024, 8), 1, 1991, 2020)

    assert result.status == "ok"
    assert result.fit.n_zero == 6
    assert result.fit.zero_probability == pytest.approx(0.2)
    assert result.window_total_mm == 0.0
    assert result.spi == pytest.approx(stats.norm.ppf(0.2), abs=1e-9)


def test_zero_total_without_any_reference_zeros_is_undefined():
    monthly = make_monthly()
    monthly[YearMonth(2024, 6)] = 0.0
    result = compute_spi(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert result.status == "undefined"
    assert result.spi is None
    assert "outside (0, 1)" in result.reason


def test_identical_reference_totals_give_an_undefined_result_not_an_error():
    monthly = make_monthly(constant=(6, 50.0))
    result = compute_spi(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert result.status == "undefined"
    assert result.spi is None
    assert result.fit is None
    assert "identical" in result.reason


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timescale": 0},
        {"timescale": 49},
        {"timescale": True},
        {"timescale": 2.5},
        {"reference_start_year": 2020, "reference_end_year": 1991},
        {"min_reference_years": 9},
        {"min_reference_years": 31},
        {"reference_start_year": 1991.0},
    ],
)
def test_invalid_parameters_are_rejected(kwargs):
    params = {
        "timescale": 3,
        "reference_start_year": 1991,
        "reference_end_year": 2020,
        "min_reference_years": 30,
    }
    params.update(kwargs)
    with pytest.raises(ValueError):
        compute_spi(
            make_monthly(),
            YearMonth(2024, 3),
            params["timescale"],
            params["reference_start_year"],
            params["reference_end_year"],
            min_reference_years=params["min_reference_years"],
        )


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf])
def test_invalid_monthly_values_are_rejected(bad):
    monthly = make_monthly()
    monthly[YearMonth(2000, 5)] = bad
    with pytest.raises(ValueError):
        compute_spi(monthly, YearMonth(2024, 3), 3, 1991, 2020)