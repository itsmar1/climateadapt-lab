"""Inspect CHIRPS GeoTIFF layout, and test whether remote single-pixel reads work.

    # Local, no network: layout and nodata tag of an already cached file
    uv run python scripts/chirps_layout_probe.py local "data/cache/chirps_v3/monthly_global/chirps-v3.0.2024.01.tif"

    # Network, tiny range requests (no full download):
    uv run python scripts/chirps_layout_probe.py remote --year 2024 --month 1 --lat 30.43 --lon -9.61

Purpose: find out whether we can read one pixel per file remotely (kilobytes) instead of
downloading ~22 MB files. Send me the output.
"""

from __future__ import annotations

import argparse
import math
import sys
import time

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.windows import Window

from climateadapt.config import get_settings
from climateadapt.data.chirps import (
    MONTHLY_GLOBAL_TIF_PATH,
    build_chirps_client,
    monthly_filename,
    sample_point,
)
from climateadapt.data.periods import YearMonth


def cmd_local(args: argparse.Namespace) -> int:
    with rasterio.open(args.path) as src:
        profile = src.profile
        print(f"driver:          {src.driver}")
        print(f"size:            {src.width} x {src.height}, bands={src.count}")
        print(f"dtype:           {src.dtypes[0]}")
        print(f"crs:             {src.crs}")
        print(f"nodata (tag):    {src.nodatavals}")
        print(f"tiled:           {profile.get('tiled')}")
        print(f"block shape:     {src.block_shapes[0]}")
        print(f"compress:        {profile.get('compress')}")
        print(f"overviews:       {src.overviews(1)}")
        print(f"image structure: {src.tags(ns='IMAGE_STRUCTURE')}")
        print(f"tags:            {src.tags()}")
    return 0


def cmd_remote(args: argparse.Namespace) -> int:
    settings = get_settings()
    month = YearMonth(args.year, args.month)
    url = f"{settings.chirps_base_url.rstrip('/')}/{MONTHLY_GLOBAL_TIF_PATH}/{monthly_filename(month)}"
    print(f"GDAL /vsicurl/ read of {url}")
    options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_USERAGENT": settings.http_user_agent,
    }
    try:
        started = time.perf_counter()
        with rasterio.Env(**options), rasterio.open("/vsicurl/" + url) as src:
            opened = time.perf_counter()
            col_f, row_f = (~src.transform) * (args.lon, args.lat)
            col, row = math.floor(col_f), math.floor(row_f)
            raw = float(src.read(1, window=Window(col, row, 1, 1))[0, 0])
            finished = time.perf_counter()
    except RasterioIOError as exc:
        print(f"Remote read FAILED: {exc}")
        return 1

    print(f"open time:   {opened - started:.2f} s")
    print(f"read time:   {finished - opened:.2f} s")
    print(f"cell (row, col) = ({row}, {col}); raw value = {raw}")

    local_client = build_chirps_client(settings)
    try:
        cached = local_client.store.cache_path_for(month)
        if cached.exists():
            sample = sample_point(cached, args.lat, args.lon)
            print(f"cached local value for comparison: {sample.value_mm}")
    finally:
        local_client.store.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    local = sub.add_parser("local", help="Print the layout of a local GeoTIFF")
    local.add_argument("path")
    local.set_defaults(func=cmd_local)

    remote = sub.add_parser("remote", help="Test a remote single-pixel read")
    remote.add_argument("--year", type=int, required=True)
    remote.add_argument("--month", type=int, required=True)
    remote.add_argument("--lat", type=float, required=True)
    remote.add_argument("--lon", type=float, required=True)
    remote.set_defaults(func=cmd_remote)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())