import math

import pytest

from climateadapt.indicators.units import (
    days_in_month,
    kelvin_to_celsius,
    mean_daily_accumulation_m_to_monthly_mm,
)


@pytest.mark.parametrize(
    ("kelvin", "celsius"), [(273.15, 0.0), (300.0, 26.85), (0.0, -273.15), (250.0, -23.15)]
)
def test_kelvin_to_celsius(kelvin, celsius):
    assert kelvin_to_celsius(kelvin) == pytest.approx(celsius)


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf, "280", None, True])
def test_kelvin_to_celsius_rejects_invalid(bad):
    with pytest.raises(ValueError):
        kelvin_to_celsius(bad)


@pytest.mark.parametrize(
    ("year", "month", "days"),
    [(2024, 2, 29), (2023, 2, 28), (1900, 2, 28), (2000, 2, 29), (2024, 1, 31), (2024, 4, 30)],
)
def test_days_in_month(year, month, days):
    assert days_in_month(year, month) == days


def test_days_in_month_rejects_bad_month():
    with pytest.raises(ValueError):
        days_in_month(2024, 13)


@pytest.mark.parametrize(
    ("mean_daily_m", "year", "month", "expected_mm"),
    [
        (0.002, 2024, 1, 62.0),  # 31 days
        (0.001, 2024, 2, 29.0),  # leap February
        (0.001, 2023, 2, 28.0),  # non-leap February
        (0.0, 2024, 6, 0.0),
    ],
)
def test_mean_daily_accumulation_to_monthly_mm(mean_daily_m, year, month, expected_mm):
    result = mean_daily_accumulation_m_to_monthly_mm(mean_daily_m, year, month)
    assert result == pytest.approx(expected_mm)


@pytest.mark.parametrize("bad", [-0.001, math.nan, math.inf, "0.1", None, True])
def test_mean_daily_accumulation_rejects_invalid(bad):
    with pytest.raises(ValueError):
        mean_daily_accumulation_m_to_monthly_mm(bad, 2024, 1)