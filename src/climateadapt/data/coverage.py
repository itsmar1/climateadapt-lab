"""Explicit coverage checks, so out-of-coverage requests fail loudly."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from numbers import Real

from climateadapt.data.errors import DataNotAvailableError, OutsideCoverageError
from climateadapt.data.periods import YearMonth


@dataclass(frozen=True)
class BoundingBox:
    """Half-open box matching raster cell semantics.

    A raster's west and north edges belong to its first cell; its east and south edges
    do not belong to any cell. So: west <= lon < east and south < lat <= north.
    """

    west: float
    south: float
    east: float
    north: float

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.west <= longitude < self.east and self.south < latitude <= self.north


# CHIRPS v3 global domain: 180W-180E, 60S-60N (Funk et al., Scientific Data 13, 718, 2026).
CHIRPS_V3_NOMINAL_BBOX = BoundingBox(west=-180.0, south=-60.0, east=180.0, north=60.0)

# CHIRPS v3 Final was back-processed from January 1981.
CHIRPS_V3_FINAL_FIRST_MONTH = YearMonth(1981, 1)


def validate_coordinates(latitude: object, longitude: object) -> tuple[float, float]:
    """Validate WGS84 decimal degrees. Raises ValueError for malformed input."""
    cleaned: list[float] = []
    for name, value, limit in (
        ("latitude", latitude, 90.0),
        ("longitude", longitude, 180.0),
    ):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a real number, got {type(value).__name__}.")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{name} must be finite, got {number}.")
        if abs(number) > limit:
            raise ValueError(f"{name} must be within +/-{limit:g} degrees, got {number}.")
        cleaned.append(number)
    return cleaned[0], cleaned[1]


def check_point_in_nominal_coverage(
    latitude: object,
    longitude: object,
    bbox: BoundingBox = CHIRPS_V3_NOMINAL_BBOX,
) -> tuple[float, float]:
    """Validate a point and require it to lie inside the nominal dataset domain.

    Being inside the domain does NOT guarantee a value: CHIRPS is land-only, so ocean
    cells (and gap cells) are returned as missing by the reader.
    """
    lat, lon = validate_coordinates(latitude, longitude)
    if not bbox.contains(lat, lon):
        raise OutsideCoverageError(
            f"Point (lat={lat}, lon={lon}) is outside the nominal CHIRPS v3 coverage "
            f"(latitude {bbox.south:g} to {bbox.north:g}, longitude {bbox.west:g} to "
            f"{bbox.east:g}; south and east edges are exclusive). No value is returned."
        )
    return lat, lon


def check_month_available(month: YearMonth, *, today: date) -> None:
    """Require a month inside the Final record's start and already ended.

    This cannot know the exact publication date of a month's Final file (CHC states it
    is typically the third week of the following month). A 404 for an ended month is
    handled by the downloader.
    """
    if month < CHIRPS_V3_FINAL_FIRST_MONTH:
        raise OutsideCoverageError(
            f"{month} is before the start of the CHIRPS v3 Final record "
            f"({CHIRPS_V3_FINAL_FIRST_MONTH})."
        )
    if month.last_day() >= today:
        raise DataNotAvailableError(
            f"{month} has not ended yet (today is {today.isoformat()}); "
            "no CHIRPS v3 Final data can exist for it."
        )