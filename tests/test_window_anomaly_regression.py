"""P04 regression guard: pins the exact temperature-anomaly behavior that the
shared ``window_anomaly`` extraction must preserve.

Inputs and expected outputs are hand-computed literals (not produced by the code
under test): reference Dec/Jan windows for 1991-2000 with Dec = 0.0 and Jan =
10.0 + 0.5 * (year - 1991), target Dec 2023 = 0.0 / Jan 2024 = 16.0, timescale 2.

Day-weighted reference means: 5.00, 5.25, ..., 7.25 (mean 6.125, an arithmetic
sequence with difference 0.25, so sample variance = 0.25^2 * (100 - 1) / 12 * 10/9
= 0.5729167). Target window mean: 8.0. Anomaly: 1.875. Percentile: 1.0.
"""

from __future__ import annotations

import math

import pytest

from climateadapt.data.periods import YearMonth
from climateadapt.indicators.temperature import compute_temperature_anomaly

EXPECTED_SD = math.sqrt(0.515625 * 10 / 9)


def test_p04_temperature_behavior_is_preserved_exactly():
    monthly = {YearMonth(1990, 12): 0.0}  # needed by the 1991 window
    for year in range(1991, 2001):
        monthly[YearMonth(year, 12)] = 0.0
        monthly[YearMonth(year, 1)] = 10.0 + 0.5 * (year - 1991)
    monthly[YearMonth(2023, 12)] = 0.0
    monthly[YearMonth(2024, 1)] = 16.0

    result = compute_temperature_anomaly(
        monthly, YearMonth(2024, 1), 2, 1991, 2000, min_reference_years=10
    )

    assert result.window_mean_c == pytest.approx(8.0)
    assert result.reference_mean_c == pytest.approx(6.125)
    assert result.anomaly_c == pytest.approx(1.875)
    assert result.reference_sd_c == pytest.approx(EXPECTED_SD)
    assert result.standardized_anomaly == pytest.approx(1.875 / EXPECTED_SD)
    assert result.percentile_rank == 1.0
    assert result.reason is None
    assert result.calendar_month == 1
    assert result.reference_years_used == list(range(1991, 2001))
    assert result.reference_years_unavailable == []
    assert result.target_in_reference_period is False
