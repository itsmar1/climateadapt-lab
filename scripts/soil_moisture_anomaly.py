"""Compute the ERA5-Land soil-moisture window anomaly for a point (needs CDS credentials).

    uv run python scripts/soil_moisture_anomaly.py --variable volumetric_soil_water_layer_1 \
        --lat 30.43 --lon -9.61 --target-end 2024-03 --timescale 3 --land-fallback-km 15

Variables: volumetric_soil_water_layer_1/2/3 (0-7, 7-28, 28-100 cm). Defaults:
reference period 1991-2020, minimum 30 reference years. A cold run makes two small
CDS requests (queue time varies). Add --full to include raw-file provenance.

Only anomalies are reported: absolute ERA5-Land soil water can be biased. Values are
in m3/m3 with a standardized anomaly; there are no category labels.
"""

from __future__ import annotations

import argparse
import json
import sys

from climateadapt.config import get_settings
from climateadapt.data.era5_land import build_era5_land_client
from climateadapt.data.errors import DataAccessError
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import DEFAULT_MIN_REFERENCE_YEARS, InsufficientReferenceError
from climateadapt.pipelines.soil_moisture_anomaly import (
    SOIL_WATER_VARIABLES,
    era5_land_soil_moisture_anomaly,
)
from climateadapt.pipelines.spi import DEFAULT_REFERENCE_END_YEAR, DEFAULT_REFERENCE_START_YEAR


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variable", choices=list(SOIL_WATER_VARIABLES), required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--target-end", type=YearMonth.parse, required=True, help="YYYY-MM")
    parser.add_argument("--timescale", type=int, required=True, help="months, 1-48")
    parser.add_argument("--reference-start-year", type=int, default=DEFAULT_REFERENCE_START_YEAR)
    parser.add_argument("--reference-end-year", type=int, default=DEFAULT_REFERENCE_END_YEAR)
    parser.add_argument("--min-reference-years", type=int, default=DEFAULT_MIN_REFERENCE_YEARS)
    parser.add_argument("--land-fallback-km", type=float, default=None)
    parser.add_argument("--full", action="store_true", help="include raw-file provenance")
    args = parser.parse_args()

    client = build_era5_land_client(get_settings())
    try:
        result = era5_land_soil_moisture_anomaly(
            client,
            variable=args.variable,
            latitude=args.lat,
            longitude=args.lon,
            target_end_month=args.target_end,
            timescale_months=args.timescale,
            reference_start_year=args.reference_start_year,
            reference_end_year=args.reference_end_year,
            min_reference_years=args.min_reference_years,
            land_fallback_max_km=args.land_fallback_km,
        )
    except (DataAccessError, InsufficientReferenceError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2

    data = result.model_dump(mode="json")
    raw_files = data.pop("raw_files")
    if args.full:
        data["raw_files"] = raw_files
    print(json.dumps(data, indent=2))
    if not args.full:
        print(f"({len(raw_files)} raw files recorded; use --full to include them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
