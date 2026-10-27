"""Fetch and print an ERA5-Land monthly point series (needs CDS credentials, see README).

    uv run python scripts/era5land_cli.py series --variable total_precipitation \
        --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03

Variables: 2m_temperature, total_precipitation, volumetric_soil_water_layer_1/2/3.
If the nearest grid point is masked (no value in any month), add --land-fallback-km 15 to
use the nearest valid neighbouring grid point within 15 km. This is opt-in and always
reported. First run submits a CDS request (queue time varies) and caches the result.
"""

from __future__ import annotations

import argparse
import sys

from climateadapt.config import get_settings
from climateadapt.data.era5_land import (
    VARIABLES,
    build_era5_land_client,
    day_weighted_mean,
    total_precipitation_mm,
)
from climateadapt.data.errors import DataAccessError, MissingDataError
from climateadapt.data.periods import YearMonth


def cmd_series(args: argparse.Namespace) -> int:
    client = build_era5_land_client(get_settings())
    try:
        series = client.monthly_point_series(
            args.variable,
            args.lat,
            args.lon,
            args.start,
            args.end,
            land_fallback_max_km=args.land_fallback_km,
        )
    except (DataAccessError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2

    print(
        f"{series.dataset_id} | {series.variable} [{series.units}] | requested "
        f"({series.requested_latitude}, {series.requested_longitude}) | grid point used "
        f"({series.grid_point_latitude}, {series.grid_point_longitude})"
    )
    info = series.land_fallback
    if info is not None:
        if info.used:
            print(f"LAND FALLBACK USED: {info.warning}")
        else:
            print(f"land fallback not used: {info.reason}")
    for value in series.values:
        shown = "MISSING" if value.value is None else f"{value.value:.4f}"
        print(f"  {value.year:04d}-{value.month:02d}  {shown:>10} {series.units}")

    try:
        if series.variable == "total_precipitation":
            print(f"window total: {total_precipitation_mm(series):.2f} mm")
        else:
            print(f"day-weighted window mean: {day_weighted_mean(series):.4f} {series.units}")
    except MissingDataError as exc:
        print(f"window aggregate: not computed ({exc})")

    for prov in series.provenance:
        print(f"  raw file: {prov.raw_file_path}  {prov.raw_file_size_bytes} bytes")
        print(f"  sha256: {prov.raw_file_sha256[:16]}...  zip: {prov.delivered_as_zip}")
    print(f"citation: {series.provenance[0].citation}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    series = sub.add_parser("series", help="Fetch and print a monthly point series")
    series.add_argument("--variable", choices=sorted(VARIABLES), required=True)
    series.add_argument("--lat", type=float, required=True)
    series.add_argument("--lon", type=float, required=True)
    series.add_argument("--start", type=YearMonth.parse, required=True, help="YYYY-MM")
    series.add_argument("--end", type=YearMonth.parse, required=True, help="YYYY-MM")
    series.add_argument(
        "--land-fallback-km",
        type=float,
        default=None,
        help="Opt in: use the nearest valid neighbouring grid point within this distance "
        "(0-25 km) if the nearest one is masked.",
    )
    series.set_defaults(func=cmd_series)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())