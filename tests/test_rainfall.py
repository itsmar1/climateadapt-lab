import math

import pytest

from climateadapt.indicators.rainfall import (
    AnomalyUndefinedError,
    InvalidPrecipitationError,
    anomaly_direction,
    percentage_anomaly,
)


@pytest.mark.parametrize(
    ("observed", "baseline", "expected"),
    [
        (80.0, 100.0, -20.0),
        (150.0, 100.0, 50.0),
        (100.0, 100.0, 0.0),
        (0.0, 100.0, -100.0),
        (200.0, 100.0, 100.0),
        (25, 50, -50.0),  # ints are accepted
        (12.5, 50.0, -75.0),
    ],
)
def test_percentage_anomaly_known_values(observed, baseline, expected):
    assert percentage_anomaly(observed, baseline) == pytest.approx(expected)


def test_result_is_not_rounded():
    assert percentage_anomaly(1.0, 3.0) == pytest.approx(-66.66666666666667)


@pytest.mark.parametrize("observed", [0.0, 10.0])
def test_zero_baseline_is_undefined(observed):
    with pytest.raises(AnomalyUndefinedError):
        percentage_anomaly(observed, 0.0)


def test_undefined_error_is_a_value_error():
    assert issubclass(AnomalyUndefinedError, ValueError)


@pytest.mark.parametrize("bad", [-0.1, -100.0])
def test_negative_observed_rejected(bad):
    with pytest.raises(InvalidPrecipitationError):
        percentage_anomaly(bad, 100.0)


@pytest.mark.parametrize("bad", [-0.1, -100.0])
def test_negative_baseline_rejected(bad):
    with pytest.raises(InvalidPrecipitationError):
        percentage_anomaly(100.0, bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_rejected(bad):
    with pytest.raises(InvalidPrecipitationError):
        percentage_anomaly(bad, 100.0)
    with pytest.raises(InvalidPrecipitationError):
        percentage_anomaly(100.0, bad)


@pytest.mark.parametrize("bad", ["100", None, True, [1.0]])
def test_non_numeric_rejected(bad):
    with pytest.raises(InvalidPrecipitationError):
        percentage_anomaly(bad, 100.0)  # type: ignore[arg-type]


def test_very_small_baseline_with_huge_observed_is_finite_or_explicitly_undefined():
    try:
        result = percentage_anomaly(1e308, 1e-300)
    except AnomalyUndefinedError:
        return
    assert math.isfinite(result)


@pytest.mark.parametrize(
    ("observed", "baseline", "expected"),
    [
        (80.0, 100.0, "below_baseline"),
        (120.0, 100.0, "above_baseline"),
        (100.0, 100.0, "equal_to_baseline"),
        (5.0, 0.0, "above_baseline"),
    ],
)
def test_anomaly_direction(observed, baseline, expected):
    assert anomaly_direction(observed, baseline) == expected