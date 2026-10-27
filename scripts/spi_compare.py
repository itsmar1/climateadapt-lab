"""Compare CHIRPS v3 and ERA5-Land SPI for one point (informational, not a verdict).

    uv run python scripts/spi_compare.py --lat 30.43 --lon -9.61 --target-end 2024-03 \
        --timescale 3 --land-fallback-km 15

Prints both SPI values and fit parameters, then the per-year reference window totals of both
products with their correlation, and the means of the first and second half of the reference
period. Two independent products agreeing on a change over time makes a single-product
artefact less likely; it is not proof. ERA5-Land does not assimilate station rainfall, so it
does not share CHIRPS's station-network changes. The first run makes a few small CDS requests
(queue time varies); CHIRPS values are read remotely and cached.
"""

from __future__ import annotations

import argparse
import statistics
import sys

from climateadapt.config import get_settings
from climateadapt.data.chirps import accumulated_total_mm, build_chirps_client
from climateadapt.data.era5_land import build_era5_land_client, total_precipitation_mm
from climateadapt.data.errors import DataAccessError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import (
    DEFAULT_MIN_REFERENCE_YEARS,
    InsufficientReferenceError,
    window_months,
)
from climateadapt.pipelines.spi import (
    DEFAULT_REFERENCE_END_YEAR,
    DEFAULT_REFERENCE_START_YEAR,
    chirps_spi,
)
from climateadapt.pipelines.spi_era5 import era5_land_spi


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _summary(name: str, result) -> None:
    print(
        f"{name:<11} SPI={_fmt(result.spi)}  P(<=window)={_fmt(result.cumulative_probability)}  "
        f"window total={result.window_total_mm:.2f} mm  gamma shape={_fmt(result.gamma_shape)} "
        f"scale={_fmt(result.gamma_scale_mm, 1)} mm  "
        f"reference years={result.reference_years_used}  "
        f"reference SPI mean/SD={_fmt(result.reference_spi_mean)}/{_fmt(result.reference_spi_std)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
    chirps = build_chirps_client(settings)
    era5 = build_era5_land_client(settings)
    try:
        common = {
            "latitude": args.lat,
            "longitude": args.lon,
            "target_end_month": args.target_end,
            "timescale_months": args.timescale,
            "reference_start_year": args.reference_start_year,
            "reference_end_year": args.reference_end_year,
            "min_reference_years": args.min_reference_years,
        }
        chirps_result = chirps_spi(chirps, **common)
        era5_result = era5_land_spi(era5, land_fallback_max_km=args.land_fallback_km, **common)

        years = sorted(
            set(chirps_result.reference_years_included)
            & set(era5_result.reference_years_included)
        )
        rows: list[tuple[int, float, float]] = []
        for year in years:
            months = window_months(YearMonth(year, args.target_end.month), args.timescale)
            c_total = accumulated_total_mm(
                chirps.monthly_point_series(args.lat, args.lon, months[0], months[-1])
            )
            e_total = total_precipitation_mm(
                era5.monthly_point_series(
                    "total_precipitation",
                    args.lat,
                    args.lon,
                    months[0],
                    months[-1],
                    land_fallback_max_km=args.land_fallback_km,
                )
            )
            rows.append((year, c_total, e_total))
    except (DataAccessError, InsufficientReferenceError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2
    finally:
        chirps.store.close()

    print(f"requested point: ({args.lat}, {args.lon})  target window ends {args.target_end}")
    print(
        f"ERA5-Land grid point used: ({era5_result.grid_point_latitude}, "
        f"{era5_result.grid_point_longitude})"
    )
    if era5_result.land_fallback is not None and era5_result.land_fallback.used:
        print(f"WARNING (ERA5-Land): {era5_result.land_fallback.warning}")
    print()
    _summary("CHIRPS v3", chirps_result)
    _summary("ERA5-Land", era5_result)

    print(f"\n{'year':<6}{'CHIRPS mm':>12}{'ERA5-Land mm':>15}")
    for year, c_total, e_total in rows:
        print(f"{year:<6}{c_total:>12.1f}{e_total:>15.1f}")

    c_values = [row[1] for row in rows]
    e_values = [row[2] for row in rows]
    try:
        correlation = statistics.correlation(c_values, e_values)
        print(f"\nPearson correlation of yearly window totals: {correlation:.2f}")
    except statistics.StatisticsError:
        print("\nPearson correlation not computable (constant or too few values).")

    half = len(rows) // 2
    if half >= 1:
        print(f"\n{'period':<14}{'CHIRPS mean mm':>16}{'ERA5-Land mean mm':>20}")
        for label, chunk in (
            (f"{rows[0][0]}-{rows[half - 1][0]}", rows[:half]),
            (f"{rows[half][0]}-{rows[-1][0]}", rows[half:]),
        ):
            print(
                f"{label:<14}{statistics.fmean(r[1] for r in chunk):>16.1f}"
                f"{statistics.fmean(r[2] for r in chunk):>20.1f}"
            )
    print(
        "\nNote: ERA5-Land does not assimilate station rainfall. Agreement between the "
        "products on a change over time makes a CHIRPS-only artefact less likely; it is not proof."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())