import math

import pytest

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import IncompleteWindowError, InsufficientReferenceError
from climateadapt.indicators.temperature import (
    compute_temperature_anomaly,
    percentile_rank,
    window_mean_c,
)

SD_OF_REFERENCE = 0.1 * math.sqrt(77.5)  # sample SD of 10 + 0.1 * (y - 2005.5), y = 1991..2020


def june_reference(first=1991, last=2020):
    """June means 10 + 0.1 * (y - 2005.5): mean 10.0, sample variance 0.01 * 77.5 (by hand)."""
    return {YearMonth(y, 6): 10.0 + 0.1 * (y - 2005.5) for y in range(first, last + 1)}


def test_window_mean_is_weighted_by_days_in_the_month():
    jan_feb_2023 = {YearMonth(2023, 1): 10.0, YearMonth(2023, 2): 20.0}
    jan_feb_2024 = {YearMonth(2024, 1): 10.0, YearMonth(2024, 2): 20.0}

    assert window_mean_c(jan_feb_2023, YearMonth(2023, 2), 2) == pytest.approx((310 + 560) / 59)
    assert window_mean_c(jan_feb_2024, YearMonth(2024, 2), 2) == pytest.approx((310 + 580) / 60)


def test_window_mean_needs_every_month():
    monthly = {YearMonth(2020, 1): 5.0, YearMonth(2020, 3): 7.0}
    assert window_mean_c(monthly, YearMonth(2020, 3), 3) is None
    assert window_mean_c(monthly, YearMonth(2020, 1), 2) is None  # needs 2019-12


def test_percentile_rank_is_a_mid_rank():
    assert percentile_rank(5.0, [1.0, 2.0, 3.0, 4.0]) == 1.0
    assert percentile_rank(0.0, [1.0, 2.0, 3.0, 4.0]) == 0.0
    assert percentile_rank(2.0, [1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.5 / 4)


def test_hand_checkable_anomaly_and_standardized_anomaly():
    monthly = june_reference()
    monthly[YearMonth(2024, 6)] = 12.0

    result = compute_temperature_anomaly(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert result.window_mean_c == pytest.approx(12.0)
    assert result.reference_mean_c == pytest.approx(10.0)
    assert result.anomaly_c == pytest.approx(2.0)
    assert result.reference_sd_c == pytest.approx(SD_OF_REFERENCE)
    assert result.standardized_anomaly == pytest.approx(2.0 / SD_OF_REFERENCE)
    assert result.percentile_rank == 1.0
    assert result.reason is None
    assert result.reference_years_used == list(range(1991, 2021))
    assert result.target_in_reference_period is False


def test_target_at_the_reference_mean_has_zero_anomaly_and_median_rank():
    monthly = june_reference()
    monthly[YearMonth(2024, 6)] = 10.0

    result = compute_temperature_anomaly(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert result.anomaly_c == pytest.approx(0.0, abs=1e-12)
    assert result.standardized_anomaly == pytest.approx(0.0, abs=1e-12)
    assert result.percentile_rank == pytest.approx(0.5)


def test_a_target_equal_to_a_reference_value_counts_half():
    monthly = june_reference()
    monthly[YearMonth(2024, 6)] = monthly[YearMonth(2000, 6)]

    result = compute_temperature_anomaly(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert result.percentile_rank == pytest.approx(9.5 / 30)  # 9 below (1991-1999) + half of 1


def test_windows_crossing_a_year_boundary_use_the_previous_december():
    monthly = {}
    for year in range(1990, 2025):
        monthly[YearMonth(year, 12)] = 2.0
        monthly[YearMonth(year, 1)] = 4.0
    monthly[YearMonth(2023, 12)] = 3.0
    monthly[YearMonth(2024, 1)] = 5.0

    result = compute_temperature_anomaly(monthly, YearMonth(2024, 1), 2, 1991, 2020)

    assert result.window_mean_c == pytest.approx(4.0)
    assert result.reference_mean_c == pytest.approx(3.0)
    assert result.anomaly_c == pytest.approx(1.0)
    assert result.reference_years_used == list(range(1991, 2021))


def test_identical_reference_means_leave_the_standardized_anomaly_undefined():
    monthly = {YearMonth(y, 6): 12.0 for y in range(1991, 2021)}
    monthly[YearMonth(2024, 6)] = 13.0

    result = compute_temperature_anomaly(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    assert result.anomaly_c == pytest.approx(1.0)
    assert result.standardized_anomaly is None
    assert "identical" in result.reason
    assert result.percentile_rank == 1.0


def test_reference_years_with_gaps_are_excluded_not_imputed():
    monthly = june_reference(first=1990)
    monthly[YearMonth(2024, 6)] = 11.0
    monthly[YearMonth(1995, 6)] = None

    with pytest.raises(InsufficientReferenceError, match="Only 29 of 30"):
        compute_temperature_anomaly(monthly, YearMonth(2024, 6), 1, 1991, 2020)

    result = compute_temperature_anomaly(
        monthly, YearMonth(2024, 6), 1, 1991, 2020, min_reference_years=20
    )
    assert result.reference_years_unavailable == [1995]
    assert len(result.reference_years_used) == 29


def test_incomplete_target_window_raises():
    monthly = june_reference()
    with pytest.raises(IncompleteWindowError, match="2024-06"):
        compute_temperature_anomaly(monthly, YearMonth(2024, 6), 1, 1991, 2020)


def test_target_inside_the_reference_period_is_flagged():
    monthly = june_reference()
    result = compute_temperature_anomaly(monthly, YearMonth(2020, 6), 1, 1991, 2020)
    assert result.target_in_reference_period is True


@pytest.mark.parametrize("bad", [290.0, 999.0, -150.0, math.nan, math.inf, True, "15"])
def test_implausible_or_invalid_temperatures_are_rejected(bad):
    monthly = june_reference()
    monthly[YearMonth(2024, 6)] = 12.0
    monthly[YearMonth(2000, 6)] = bad
    with pytest.raises(ValueError):
        compute_temperature_anomaly(monthly, YearMonth(2024, 6), 1, 1991, 2020)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timescale": 0},
        {"timescale": 49},
        {"reference_start_year": 2020, "reference_end_year": 1991},
        {"min_reference_years": 9},
        {"min_reference_years": 31},
    ],
)
def test_invalid_parameters_are_rejected(kwargs):
    params = {
        "timescale": 1,
        "reference_start_year": 1991,
        "reference_end_year": 2020,
        "min_reference_years": 30,
    }
    params.update(kwargs)
    monthly = june_reference()
    monthly[YearMonth(2024, 6)] = 12.0
    with pytest.raises(ValueError):
        compute_temperature_anomaly(
            monthly,
            YearMonth(2024, 6),
            params["timescale"],
            params["reference_start_year"],
            params["reference_end_year"],
            min_reference_years=params["min_reference_years"],
        )