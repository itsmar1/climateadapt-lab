"""Developer utility to verify CHIRPS v3 access from your own machine.

    uv run python scripts/chirps_cli.py probe --year 2024 --month 1
    uv run python scripts/chirps_cli.py series --lat 30.4 --lon -9.6 --start 2024-01 --end 2024-03

`probe` sends one HEAD request (no file download) and prints status and size.
`series` downloads the needed monthly files into the cache, then prints values and
provenance. Run `probe` first so you know the file size before downloading.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from climateadapt.config import get_settings
from climateadapt.data.chirps import (
    MONTHLY_GLOBAL_TIF_PATH,
    accumulated_total_mm,
    build_chirps_client,
    monthly_filename,
)
from climateadapt.data.errors import DataAccessError, MissingDataError
from climateadapt.data.periods import YearMonth


def cmd_probe(args: argparse.Namespace) -> int:
    settings = get_settings()
    month = YearMonth(args.year, args.month)
    base = settings.chirps_base_url.rstrip("/")
    url = f"{base}/{MONTHLY_GLOBAL_TIF_PATH}/{monthly_filename(month)}"
    print(f"HEAD {url}")
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.http_user_agent},
        ) as client:
            response = client.head(url)
    except httpx.HTTPError as exc:
        print(f"Network error: {exc}")
        return 2
    print(f"status:         {response.status_code}")
    print(f"final url:      {response.url}")
    print(f"content-type:   {response.headers.get('content-type')}")
    print(f"content-length: {response.headers.get('content-length')}")
    print(f"last-modified:  {response.headers.get('last-modified')}")
    return 0 if response.status_code == 200 else 1


def cmd_series(args: argparse.Namespace) -> int:
    settings = get_settings()
    client = build_chirps_client(settings)
    try:
        series = client.monthly_point_series(args.lat, args.lon, args.start, args.end)
    except (DataAccessError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 2
    finally:
        client.store.close()

    print(
        f"CHIRPS v{series.version} {series.product} | requested "
        f"({series.requested_latitude}, {series.requested_longitude}) | cell centre "
        f"({series.pixel_center_latitude:.4f}, {series.pixel_center_longitude:.4f})"
    )
    for value in series.values:
        shown = "MISSING" if value.precipitation_mm is None else f"{value.precipitation_mm:.2f}"
        print(f"  {value.year:04d}-{value.month:02d}  {shown:>10} {series.units}")
    try:
        print(f"accumulated total: {accumulated_total_mm(series):.2f} mm")
    except MissingDataError as exc:
        print(f"accumulated total: not computed ({exc})")
    for prov in series.provenance:
        print(f"  {prov.source_url}  {prov.size_bytes} bytes  sha256={prov.sha256[:12]}...")
    print(f"citation: {series.provenance[0].citation}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="HEAD-check one monthly file URL")
    probe.add_argument("--year", type=int, required=True)
    probe.add_argument("--month", type=int, required=True)
    probe.set_defaults(func=cmd_probe)

    series = sub.add_parser("series", help="Fetch and print a monthly point series")
    series.add_argument("--lat", type=float, required=True)
    series.add_argument("--lon", type=float, required=True)
    series.add_argument("--start", type=YearMonth.parse, required=True, help="YYYY-MM")
    series.add_argument("--end", type=YearMonth.parse, required=True, help="YYYY-MM")
    series.set_defaults(func=cmd_series)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())