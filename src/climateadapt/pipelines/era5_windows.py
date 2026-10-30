"""Shared ERA5-Land window assembly for the point pipelines (P04, KI-16).

``spi_era5`` and ``temperature_anomaly`` duplicated this logic; the soil-moisture
pipeline is the third user. Everything here is a verbatim move of the shared
behavior: reference-window planning with pre-record exclusion, fail-fast month
validation, target-first fetch, one grouped CDS request per identical month-set,
per-window reads, and the same-grid-point refusal. Pipelines keep their own
indicator computation, result models, and limitation lists.
"""

from __future__ import annotations

import math
from itertools import chain

from climateadapt.data.coverage import ERA5_LAND_FIRST_MONTH
from climateadapt.data.era5_land import Era5LandClient, Era5PointSeries, VariableSpec
from climateadapt.data.errors import DataIntegrityError, MissingDataError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import window_months


def plan_era5_reference_windows(
    target_end_month: YearMonth,
    timescale_months: int,
    reference_start_year: int,
    reference_end_year: int,
) -> tuple[list[YearMonth], dict[int, list[YearMonth]], dict[int, str]]:
    """Target months plus per-year reference windows for the same calendar window.

    Years whose window starts before the ERA5-Land monthly record are excluded here
    (with reasons) instead of being requested.
    """
    target_months = window_months(target_end_month, timescale_months)
    windows: dict[int, list[YearMonth]] = {}
    pipeline_reasons: dict[int, str] = {}
    for year in range(reference_start_year, reference_end_year + 1):
        months = window_months(YearMonth(year, target_end_month.month), timescale_months)
        if months[0] < ERA5_LAND_FIRST_MONTH:
            pipeline_reasons[year] = (
                f"the window starts at {months[0]}, before the ERA5-Land monthly record begins "
                f"({ERA5_LAND_FIRST_MONTH})"
            )
            continue
        windows[year] = months
    return target_months, windows, pipeline_reasons


def fetch_era5_window_values(
    client: Era5LandClient,
    spec: VariableSpec,
    lat: float,
    lon: float,
    target_months: list[YearMonth],
    windows: dict[int, list[YearMonth]],
    *,
    land_fallback_max_km: float | None,
    incomplete_window_message: str,
) -> tuple[dict[YearMonth, float | None], list[Era5PointSeries]]:
    """Fetch target-first, then grouped reference months; refuse mixed grid points.

    Returns the combined monthly mapping and every per-window series (target first).
    Raises MissingDataError (with ``incomplete_window_message``) on an incomplete
    target window and DataIntegrityError if windows resolve to different grid points.
    """
    # Fail fast: validate every month BEFORE any request to the CDS.
    for month in chain(target_months, *windows.values()):
        client.store.assert_month_available(month)

    target_series = client.monthly_point_series(
        spec.cds_name,
        lat,
        lon,
        target_months[0],
        target_months[-1],
        land_fallback_max_km=land_fallback_max_km,
    )
    missing = [f"{v.year:04d}-{v.month:02d}" for v in target_series.values if v.value is None]
    if missing:
        raise MissingDataError(
            "The target window has no value for: " + ", ".join(missing) + ". "
            + incomplete_window_message
        )

    # One grouped CDS request per identical month-set; later per-window reads hit the cache.
    needed = sorted({month for months in windows.values() for month in months})
    if needed:
        client.store.get_records(spec, lat, lon, needed)

    monthly: dict[YearMonth, float | None] = {}
    all_series = [target_series]
    for v in target_series.values:
        monthly[YearMonth(v.year, v.month)] = v.value
    for months in windows.values():
        series = client.monthly_point_series(
            spec.cds_name,
            lat,
            lon,
            months[0],
            months[-1],
            land_fallback_max_km=land_fallback_max_km,
        )
        all_series.append(series)
        for v in series.values:
            monthly[YearMonth(v.year, v.month)] = v.value

    reference = all_series[0]
    for series in all_series[1:]:
        if not (
            math.isclose(series.grid_point_latitude, reference.grid_point_latitude, abs_tol=1e-6)
            and math.isclose(
                series.grid_point_longitude, reference.grid_point_longitude, abs_tol=1e-6
            )
        ):
            raise DataIntegrityError(
                "Grid point differs between windows (a different neighbouring grid point would "
                "have been chosen for some reference years); refusing to combine them."
            )

    return monthly, all_series
