"""Unit conversions, kept as tested pure functions (never delegated to an LLM)."""

from __future__ import annotations

import calendar
import math
from numbers import Real

KELVIN_OFFSET = 273.15


def _finite_real(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number, got {type(value).__name__}.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {number}.")
    return number


def days_in_month(year: int, month: int) -> int:
    """Calendar days in a month (Gregorian, leap years handled)."""
    return calendar.monthrange(year, month)[1]


def kelvin_to_celsius(value_k: float) -> float:
    """Convert kelvin to degrees Celsius. Raises ValueError for invalid or negative kelvin."""
    kelvin = _finite_real("temperature (K)", value_k)
    if kelvin < 0:
        raise ValueError(f"temperature (K) cannot be negative, got {kelvin}.")
    return kelvin - KELVIN_OFFSET


def mean_daily_accumulation_m_to_monthly_mm(mean_daily_m: float, year: int, month: int) -> float:
    """Convert a monthly mean of DAILY accumulations (metres/day) to mm per month.

    ERA5-Land monthly means of daily means store accumulated variables (such as total
    precipitation) as a mean daily accumulation, so the monthly total is
    ``mean_daily_m * 1000 * days_in_month``.
    """
    value = _finite_real("mean daily accumulation (m/day)", mean_daily_m)
    if value < 0:
        raise ValueError(f"mean daily accumulation cannot be negative, got {value}.")
    return value * 1000.0 * days_in_month(year, month)