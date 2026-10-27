"""Compare CHIRPS v3 and ERA5-Land monthly precipitation for one point (informational).

    uv run python scripts/compare_chirps_era5.py --lat 30.43 --lon -9.61 \
        --start 2024-01 --end 2024-03 --land-fallback-km 15

Two independent products disagreeing is a measure of uncertainty. It is not evidence that
either one is correct; only observations at the location can settle that.
"""

from __future__ import annotations

import argparse
import sys

from climateadapt.config import get_settings
from climateadapt.data.chirps import accumulated_total_mm, build_chirps_client
from climateadapt.data.era5_land import build_era5_land_client, total_precipitation_mm
from climateadapt.data.errors import DataAccessError, MissingDataError
from climateadapt.data.periods import YearMonth


def _fmt(value: float | None) -> str:
    return "MISSING" if value is None else f"{value:.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", type=YearMonth.parse, required=True, help="YYYY-MM")
    parser.add_argument("--end", type=YearMonth.parse, required=True, help="YYYY-MM")
    parser.add_argument("--land-fallback-km", type=float, default=None)
    args = parser.parse_args()

    settings = get_settings()
    chirps = build_chirps_client(settings)
    era5 = build_era5_land_client(settings)
    try:
        chirps_series = chirps.monthly_point_series(args.lat, args.lon, args.start, args.end)
        era5_series = era5.monthly_point_series(
            "total_precipitation",
            args.lat,
            args.lon,
            args.start,
            args.end,
            land_fallback_max_km=args.land_fallback_km,
        )
    except (DataAccessError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2
    finally:
        chirps.store.close()

    print(f"requested point: ({args.lat}, {args.lon})")
    print(
        f"CHIRPS cell centre:  ({chirps_series.pixel_center_latitude:.4f}, "
        f"{chirps_series.pixel_center_longitude:.4f})"
    )
    print(
        f"ERA5-Land grid point: ({era5_series.grid_point_latitude}, "
        f"{era5_series.grid_point_longitude})"
    )
    if chirps_series.point_on_cell_boundary:
        print("WARNING (CHIRPS): the point lies on a cell edge or corner.")
    if era5_series.land_fallback is not None and era5_series.land_fallback.used:
        print(f"WARNING (ERA5-Land): {era5_series.land_fallback.warning}")

    print(f"\n{'month':<9}{'CHIRPS mm':>12}{'ERA5-Land mm':>15}{'ERA5 - CHIRPS':>16}")
    for c, e in zip(chirps_series.values, era5_series.values, strict=True):
        if c.precipitation_mm is None or e.value is None:
            diff = "n/a"
        else:
            diff = f"{e.value - c.precipitation_mm:+.2f}"
        print(
            f"{c.year:04d}-{c.month:02d}  {_fmt(c.precipitation_mm):>12}"
            f"{_fmt(e.value):>15}{diff:>16}"
        )

    try:
        chirps_total = accumulated_total_mm(chirps_series)
        era5_total = total_precipitation_mm(era5_series)
        print(
            f"\nwindow totals: CHIRPS {chirps_total:.2f} mm | ERA5-Land {era5_total:.2f} mm | "
            f"difference {era5_total - chirps_total:+.2f} mm"
        )
    except MissingDataError as exc:
        print(f"\nwindow totals not computed: {exc}")

    print(
        "\nNote: CHIRPS blends satellite estimates with gauge stations; ERA5-Land precipitation "
        "is model-derived. Their disagreement is an uncertainty signal, not a verdict."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())