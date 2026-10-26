"""Rainfall indicators.

IMPORTANT SCIENTIFIC LIMITATION
-------------------------------
The percentage anomaly implemented here is a simple prototype indicator. It is NOT a
calibrated drought index and must not be used alone to classify drought severity.
The same percentage deficit can mean very different things in different climates, seasons,
and rainfall regimes. Standardised indicators such as SPI will be added in a later milestone.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Literal

FORMULA = "((observed_total - baseline_mean) / baseline_mean) * 100"

LIMITATIONS: tuple[str, ...] = (
    "This is a simple percentage anomaly of accumulated precipitation, not a calibrated "
    "drought index.",
    "It must not be used alone to classify drought severity; the same percentage anomaly "
    "has different meaning in different climates and seasons.",
    "The result is only as valid as the supplied totals: the observation period and the "
    "baseline reference period must cover the same calendar window and be consistent in "
    "units (millimetres) and data source.",
    "No data source, spatial coverage, or temporal validity has been checked by this "
    "calculation.",
)

Direction = Literal["below_baseline", "above_baseline", "equal_to_baseline"]


class InvalidPrecipitationError(ValueError):
    """Raised when a precipitation value is not a finite, non-negative real number."""


class AnomalyUndefinedError(ValueError):
    """Raised when the percentage anomaly is mathematically undefined or not representable."""


def _validate_precipitation_mm(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InvalidPrecipitationError(
            f"{name} must be a real number in millimetres, got {type(value).__name__}."
        )
    number = float(value)
    if not math.isfinite(number):
        raise InvalidPrecipitationError(f"{name} must be finite, got {number}.")
    if number < 0:
        raise InvalidPrecipitationError(
            f"{name} must be non-negative (precipitation totals cannot be negative), "
            f"got {number}."
        )
    return number


def percentage_anomaly(observed_total_mm: float, baseline_mean_mm: float) -> float:
    """Return the percentage precipitation anomaly relative to a baseline mean.

    percentage_anomaly = ((observed_total - baseline_mean) / baseline_mean) * 100

    Args:
        observed_total_mm: Observed-period precipitation total, in millimetres.
        baseline_mean_mm: Historical baseline mean for the same window, in millimetres.

    Returns:
        The anomaly in percent (negative = below baseline). Not rounded.

    Raises:
        InvalidPrecipitationError: A value is non-numeric, boolean, non-finite, or negative.
        AnomalyUndefinedError: The baseline is zero (division by zero), or the result
            cannot be represented as a finite number.
    """
    observed = _validate_precipitation_mm("observed_total_mm", observed_total_mm)
    baseline = _validate_precipitation_mm("baseline_mean_mm", baseline_mean_mm)

    if baseline == 0.0:
        raise AnomalyUndefinedError(
            "Percentage anomaly is undefined when the baseline mean is 0 mm "
            "(division by zero). Use a different indicator or a longer/wetter baseline window."
        )

    try:
        result = ((observed - baseline) / baseline) * 100.0
    except OverflowError as exc:  # pragma: no cover - platform dependent
        raise AnomalyUndefinedError("Percentage anomaly is not representable.") from exc

    if not math.isfinite(result):
        raise AnomalyUndefinedError("Percentage anomaly is not representable as a finite number.")
    return result


def anomaly_direction(observed_total_mm: float, baseline_mean_mm: float) -> Direction:
    """Return a neutral description of observed vs baseline. This is NOT a severity class."""
    observed = _validate_precipitation_mm("observed_total_mm", observed_total_mm)
    baseline = _validate_precipitation_mm("baseline_mean_mm", baseline_mean_mm)
    if observed < baseline:
        return "below_baseline"
    if observed > baseline:
        return "above_baseline"
    return "equal_to_baseline"