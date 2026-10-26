"""Fetch and print an ERA5-Land monthly point series (needs CDS credentials, see README).

    uv run python scripts/era5land_cli.py series --variable total_precipitation \
        --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03

First run submits a CDS request (queue time varies) and caches the result; later runs for
the same point and months are served from disk.
"""

from __future__ import annotations

import argparse
import sys

from climateadapt.config import get_settings
from climateadapt.data.era5_land import (
    VARIABLES,
    build_era5_land_client,
    day_weighted_mean_temperature_c,
    total_precipitation_mm,
)
from climateadapt.data.errors import DataAccessError, MissingDataError
from climateadapt.data.periods import YearMonth


def cmd_series(args: argparse.Namespace) -> int:
    client = build_era5_land_client(get_settings())
    try:
        series = client.monthly_point_series(
            args.variable, args.lat, args.lon, args.start, args.end
        )
    except (DataAccessError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2

    print(
        f"{series.dataset_id} | {series.variable} [{series.units}] | requested "
        f"({series.requested_latitude}, {series.requested_longitude}) | grid point "
        f"({series.grid_point_latitude}, {series.grid_point_longitude})"
    )
    for value in series.values:
        shown = "MISSING" if value.value is None else f"{value.value:.3f}"
        extra = f"  note: {'; '.join(value.notes)}" if value.notes else ""
        print(f"  {value.year:04d}-{value.month:02d}  {shown:>10} {series.units}{extra}")

    try:
        if series.variable == "total_precipitation":
            print(f"window total: {total_precipitation_mm(series):.2f} mm")
        else:
            print(f"day-weighted window mean: {day_weighted_mean_temperature_c(series):.2f} degC")
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
    series.set_defaults(func=cmd_series)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())