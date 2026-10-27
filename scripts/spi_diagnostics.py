"""SPI fit diagnostics for one point and window: does the gamma assumption matter?

    uv run python scripts/spi_diagnostics.py --source chirps --lat 30.43 --lon -9.61 \
        --target-end 2024-03 --timescale 3
    uv run python scripts/spi_diagnostics.py --source era5 --lat 30.43 --lon -9.61 \
        --target-end 2024-03 --timescale 3 --land-fallback-km 15

Uses cached data when you have already run the SPI scripts for the same point and window
(no new network requests then). Descriptive only: no pass/fail threshold.
"""

from __future__ import annotations

import argparse
import math
import sys

from climateadapt.config import get_settings
from climateadapt.data.chirps import build_chirps_client
from climateadapt.data.coverage import (
    CHIRPS_V3_FINAL_FIRST_MONTH,
    ERA5_LAND_FIRST_MONTH,
    ERA5_LAND_NOMINAL_BBOX,
    check_point_in_nominal_coverage,
)
from climateadapt.data.era5_land import VARIABLES, build_era5_land_client
from climateadapt.data.errors import DataAccessError, DataIntegrityError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    DEFAULT_MIN_REFERENCE_YEARS,
    GammaFitError,
    IncompleteWindowError,
    InsufficientReferenceError,
    window_months,
)
from climateadapt.indicators.spi_diagnostics import compute_spi_fit_diagnostics
from climateadapt.pipelines.spi import DEFAULT_REFERENCE_END_YEAR, DEFAULT_REFERENCE_START_YEAR


def _windows(target_end, k, ref_start, ref_end, first_month):
    windows = [window_months(target_end, k)]
    for year in range(ref_start, ref_end + 1):
        months = window_months(YearMonth(year, target_end.month), k)
        if months[0] >= first_month:
            windows.append(months)
    return windows


def collect_chirps(client, lat, lon, windows):
    client.prefetch(lat, lon, window_months_union(windows))
    monthly = {}
    for months in windows:
        series = client.monthly_point_series(lat, lon, months[0], months[-1])
        for v in series.values:
            monthly[YearMonth(v.year, v.month)] = v.precipitation_mm
    return monthly


def window_months_union(windows):
    return sorted({month for months in windows for month in months})


def collect_era5(client, lat, lon, windows, fallback_km):
    check_point_in_nominal_coverage(lat, lon, ERA5_LAND_NOMINAL_BBOX, dataset="ERA5-Land")
    spec = VARIABLES["total_precipitation"]
    monthly = {}
    grid = None

    def absorb(months):
        nonlocal grid
        series = client.monthly_point_series(
            "total_precipitation",
            lat,
            lon,
            months[0],
            months[-1],
            land_fallback_max_km=fallback_km,
        )
        point = (series.grid_point_latitude, series.grid_point_longitude)
        if grid is None:
            grid = point
        elif point != grid:
            raise DataIntegrityError("Grid point differs between windows; refusing to combine.")
        for v in series.values:
            monthly[YearMonth(v.year, v.month)] = v.value

    absorb(windows[0])  # target first: a masked point fails before any large request
    reference_months = window_months_union(windows[1:])
    if reference_months:
        client.store.get_records(spec, lat, lon, reference_months)  # grouped requests
    for months in windows[1:]:
        absorb(months)
    return monthly, grid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=("chirps", "era5"), required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--target-end", type=YearMonth.parse, required=True, help="YYYY-MM")
    parser.add_argument("--timescale", type=int, required=True)
    parser.add_argument("--reference-start-year", type=int, default=DEFAULT_REFERENCE_START_YEAR)
    parser.add_argument("--reference-end-year", type=int, default=DEFAULT_REFERENCE_END_YEAR)
    parser.add_argument("--min-reference-years", type=int, default=DEFAULT_MIN_REFERENCE_YEARS)
    parser.add_argument("--land-fallback-km", type=float, default=None)
    args = parser.parse_args()

    settings = get_settings()
    grid_note = ""
    try:
        if args.source == "chirps":
            client = build_chirps_client(settings)
            try:
                windows = _windows(
                    args.target_end,
                    args.timescale,
                    args.reference_start_year,
                    args.reference_end_year,
                    CHIRPS_V3_FINAL_FIRST_MONTH,
                )
                monthly = collect_chirps(client, args.lat, args.lon, windows)
            finally:
                client.store.close()
            label = "CHIRPS v3 Final"
        else:
            client = build_era5_land_client(settings)
            windows = _windows(
                args.target_end,
                args.timescale,
                args.reference_start_year,
                args.reference_end_year,
                ERA5_LAND_FIRST_MONTH,
            )
            monthly, grid = collect_era5(client, args.lat, args.lon, windows, args.land_fallback_km)
            label = "ERA5-Land monthly means"
            grid_note = f"  grid point used: {grid}"

        diag = compute_spi_fit_diagnostics(
            monthly,
            args.target_end,
            args.timescale,
            args.reference_start_year,
            args.reference_end_year,
            min_reference_years=args.min_reference_years,
        )
    except (
        DataAccessError,
        GammaFitError,
        IncompleteWindowError,
        InsufficientReferenceError,
        ValueError,
    ) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2

    def fmt(value, digits=3):
        return "n/a" if value is None else f"{value:+.{digits}f}"

    print(f"{label}  point ({args.lat}, {args.lon}){grid_note}")
    print(
        f"target window ends {args.target_end} (SPI-{args.timescale}); reference "
        f"{args.reference_start_year}-{args.reference_end_year}, "
        f"{diag.n_reference_years} usable years"
    )
    print(
        f"SPI (gamma fit):            {fmt(diag.spi_gamma)}   "
        f"P(<= window) = {diag.gamma_cumulative_probability:.3f}"
    )
    print(
        f"SPI (empirical mid-rank):   {fmt(diag.spi_empirical)}   "
        f"P(<= window) = {diag.empirical_cumulative_probability:.3f}"
    )
    print(f"difference (empirical - gamma): {fmt(diag.spi_difference)}")
    print(f"max CDF deviation (KS D):   {diag.max_cdf_deviation:.3f}")
    reference_d = 1.36 / math.sqrt(diag.n_reference_years)
    print(
        f"(reference only: the asymptotic 5% KS critical value for a FULLY SPECIFIED "
        f"distribution is about {reference_d:.3f} for n={diag.n_reference_years}. Parameters "
        "estimated from the same sample make the test more demanding, so a smaller D does not "
        "establish a good fit.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())