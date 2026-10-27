"""Compute CHIRPS-based SPI for a point from the command line.

    uv run python scripts/chirps_spi.py --lat 30.43 --lon -9.61 --target-end 2024-03 --timescale 3

Defaults: reference period 1991-2020, minimum 30 reference years. A cold run reads about
timescale x reference-years monthly values (also warms the cache for later API calls).
Add --full to include the per-file provenance list.
"""

from __future__ import annotations

import argparse
import json
import sys

from climateadapt.config import get_settings
from climateadapt.data.chirps import build_chirps_client
from climateadapt.data.errors import DataAccessError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import DEFAULT_MIN_REFERENCE_YEARS, InsufficientReferenceError
from climateadapt.pipelines.spi import (
    DEFAULT_REFERENCE_END_YEAR,
    DEFAULT_REFERENCE_START_YEAR,
    chirps_spi,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--target-end", type=YearMonth.parse, required=True, help="YYYY-MM")
    parser.add_argument("--timescale", type=int, required=True, help="months, 1-48")
    parser.add_argument("--reference-start-year", type=int, default=DEFAULT_REFERENCE_START_YEAR)
    parser.add_argument("--reference-end-year", type=int, default=DEFAULT_REFERENCE_END_YEAR)
    parser.add_argument("--min-reference-years", type=int, default=DEFAULT_MIN_REFERENCE_YEARS)
    parser.add_argument("--full", action="store_true", help="include source file provenance")
    args = parser.parse_args()

    settings = get_settings()
    n_years = args.reference_end_year - args.reference_start_year + 1
    print(
        f"Reading up to {(n_years + 1) * args.timescale} monthly values "
        f"(access mode: {settings.chirps_access}; cached values are reused).",
        file=sys.stderr,
    )

    client = build_chirps_client(settings)
    try:
        result = chirps_spi(
            client,
            latitude=args.lat,
            longitude=args.lon,
            target_end_month=args.target_end,
            timescale_months=args.timescale,
            reference_start_year=args.reference_start_year,
            reference_end_year=args.reference_end_year,
            min_reference_years=args.min_reference_years,
        )
    except (DataAccessError, InsufficientReferenceError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2
    finally:
        client.store.close()

    data = result.model_dump(mode="json")
    files = data.pop("source_files")
    if args.full:
        data["source_files"] = files
    print(json.dumps(data, indent=2))
    if not args.full:
        print(f"({len(files)} source files recorded; use --full to include them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())