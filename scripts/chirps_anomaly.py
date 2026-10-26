"""Run the CHIRPS rainfall-anomaly pipeline from the command line.

Running this once also warms the local cache, so later API calls for the same period are
served from disk.

    uv run python scripts/chirps_anomaly.py --lat 30.4 --lon -9.6 \
        --observed-start 2024-01 --window-months 3 \
        --baseline-start-year 2011 --baseline-end-year 2020

The first run downloads (baseline years x window months) + window months monthly files.
"""

from __future__ import annotations

import argparse
import sys

from climateadapt.config import get_settings
from climateadapt.data.chirps import build_chirps_client
from climateadapt.data.errors import DataAccessError
from climateadapt.data.periods import YearMonth
from climateadapt.pipelines.rainfall_anomaly import (
    MIN_BASELINE_YEARS_DEFAULT,
    InsufficientBaselineError,
    chirps_rainfall_anomaly,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--observed-start", type=YearMonth.parse, required=True, help="YYYY-MM")
    parser.add_argument("--window-months", type=int, required=True)
    parser.add_argument("--baseline-start-year", type=int, required=True)
    parser.add_argument("--baseline-end-year", type=int, required=True)
    parser.add_argument("--min-baseline-years", type=int, default=MIN_BASELINE_YEARS_DEFAULT)
    args = parser.parse_args()

    n_years = args.baseline_end_year - args.baseline_start_year + 1
    print(
        f"Up to {(n_years + 1) * args.window_months} monthly files are needed "
        "(files already cached are reused)."
    )

    client = build_chirps_client(get_settings())
    try:
        result = chirps_rainfall_anomaly(
            client,
            latitude=args.lat,
            longitude=args.lon,
            observed_start=args.observed_start,
            window_months_count=args.window_months,
            baseline_start_year=args.baseline_start_year,
            baseline_end_year=args.baseline_end_year,
            min_baseline_years=args.min_baseline_years,
        )
    except (DataAccessError, InsufficientBaselineError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2
    finally:
        client.store.close()

    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())