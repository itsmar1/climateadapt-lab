import math

import pytest

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.soil_moisture import compute_soil_moisture_anomaly
from climateadapt.indicators.spi import IncompleteWindowError, InsufficientReferenceError
from climateadapt.indicators.window_anomaly import (
    compute_window_anomaly,
    mid_rank_percentile,
    window_day_weighted_mean,
)

SD_OF_REFERENCE = 0.01 * math.sqrt(77.5)  # sample SD of 0.10 + 0.01 * i, i = 0..29


def jan_reference(first=1991, last=2020):
    """January means 0.10 + 0.01 * (y - 1991): mean 0.245, known sample variance."""
    return {YearMonth(y, 1): 0.10 + 0.01 * (y - 1991) for y in range(first, last + 1)}


def test_window_mean_is_weighted_by_days_in_the_month():
    jan_feb_2023 = {YearMonth(2023, 1): 0.10, YearMonth(2023, 2): 0.20}
    jan_feb_2024 = {YearMonth(2024, 1): 0.10, YearMonth(2024, 2): 0.20}

    assert window_day_weighted_mean(jan_feb_2023, YearMonth(2023, 2), 2) == pytest.approx(
        (3.1 + 5.6) / 59
    )
    assert window_day_weighted_mean(jan_feb_2024, YearMonth(2024, 2), 2) == pytest.approx(
        (3.1 + 5.8) / 60
    )


def test_window_mean_needs_every_month():
    monthly = {YearMonth(2020, 1): 0.2, YearMonth(2020, 3): 0.3}
    assert window_day_weighted_mean(monthly, YearMonth(2020, 3), 3) is None


def test_mid_rank_percentile():
    assert mid_rank_percentile(0.5, [0.1, 0.2, 0.3, 0.4]) == 1.0
    assert mid_rank_percentile(0.0, [0.1, 0.2, 0.3, 0.4]) == 0.0
    assert mid_rank_percentile(0.2, [0.1, 0.2, 0.3, 0.4]) == pytest.approx(1.5 / 4)


def test_hand_checkable_anomaly_and_standardized_anomaly():
    monthly = jan_reference()
    monthly[YearMonth(2024, 1)] = 0.45

    result = compute_soil_moisture_anomaly(monthly, YearMonth(2024, 1), 1, 1991, 2020)

    assert result.window_mean_m3m3 == pytest.approx(0.45)
    assert result.reference_mean_m3m3 == pytest.approx(0.245)
    assert result.anomaly_m3m3 == pytest.approx(0.205)
    assert result.reference_sd_m3m3 == pytest.approx(SD_OF_REFERENCE)
    assert result.standardized_anomaly == pytest.approx(0.205 / SD_OF_REFERENCE)
    assert result.percentile_rank == 1.0
    assert result.reason is None
    assert result.reference_years_used == list(range(1991, 2021))
    assert result.target_in_reference_period is False


def test_identical_reference_means_leave_the_standardized_anomaly_undefined():
    monthly = {YearMonth(y, 1): 0.20 for y in range(1991, 2021)}
    monthly[YearMonth(2024, 1)] = 0.25

    result = compute_soil_moisture_anomaly(monthly, YearMonth(2024, 1), 1, 1991, 2020)

    assert result.anomaly_m3m3 == pytest.approx(0.05)
    assert result.standardized_anomaly is None
    assert "identical" in result.reason


def test_reference_years_with_gaps_are_excluded_not_imputed():
    monthly = jan_reference()
    monthly[YearMonth(2024, 1)] = 0.30
    monthly[YearMonth(1995, 1)] = None

    with pytest.raises(InsufficientReferenceError, match="Only 29 of 30"):
        compute_soil_moisture_anomaly(monthly, YearMonth(2024, 1), 1, 1991, 2020)

    result = compute_soil_moisture_anomaly(
        monthly, YearMonth(2024, 1), 1, 1991, 2020, min_reference_years=20
    )
    assert result.reference_years_unavailable == [1995]
    assert len(result.reference_years_used) == 29


def test_incomplete_target_window_raises():
    monthly = jan_reference()
    with pytest.raises(IncompleteWindowError, match="2024-01"):
        compute_soil_moisture_anomaly(monthly, YearMonth(2024, 1), 1, 1991, 2020)


@pytest.mark.parametrize("bad", [-0.1, 1.5, math.nan, math.inf, True, "0.2"])
def test_implausible_or_invalid_soil_water_is_rejected(bad):
    monthly = jan_reference()
    monthly[YearMonth(2024, 1)] = 0.30
    monthly[YearMonth(2000, 1)] = bad
    with pytest.raises(ValueError):
        compute_soil_moisture_anomaly(monthly, YearMonth(2024, 1), 1, 1991, 2020)


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
    monthly = jan_reference()
    monthly[YearMonth(2024, 1)] = 0.30
    with pytest.raises(ValueError):
        compute_soil_moisture_anomaly(
            monthly,
            YearMonth(2024, 1),
            params["timescale"],
            params["reference_start_year"],
            params["reference_end_year"],
            min_reference_years=params["min_reference_years"],
        )


def test_generic_core_accepts_no_validity_check():
    monthly = jan_reference()
    monthly[YearMonth(2024, 1)] = 0.30
    result = compute_window_anomaly(
        monthly, YearMonth(2024, 1), 1, 1991, 2020, check_value=None
    )
    assert result.anomaly == pytest.approx(0.055)
    assert result.reference_years_used == list(range(1991, 2021))
