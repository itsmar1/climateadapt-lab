"""Shared helpers for ERA5-Land tests: a synthetic CDS-like NetCDF builder and a fake downloader.

All data here is SYNTHETIC. Nothing touches the network or needs credentials.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import xarray as xr

LAT, LON = 30.43, -9.61  # nearest 0.1 degree grid point is (30.4, -9.6)


def axis(low: float, high: float) -> list[float]:
    ints = range(math.ceil(low * 10 - 1e-9), math.floor(high * 10 + 1e-9) + 1)
    return [i / 10 for i in ints]


def cell_value(year: int, month: int, lat: float, lon: float) -> float:
    """A distinct positive value (m/day) per cell and month, to identify chosen cells."""
    return 0.001 * month + 0.0001 * round((lat - 30.0) * 10) + 0.00001 * round((lon + 10.0) * 10)


class Builder:
    """Write a synthetic CDS-like NetCDF that honours the request's years/months/area."""

    def __init__(self, value_fn, *, var="t2m", units="K"):
        self.value_fn = value_fn
        self.var = var
        self.units = units

    def __call__(self, request, target: Path) -> None:
        north, west, south, east = request["area"]
        lats = list(reversed(axis(south, north)))
        lons = axis(west, east)
        years = sorted(int(y) for y in request["year"])
        months = sorted(int(m) for m in request["month"])
        stamps = [(y, m) for y in years for m in months]
        times = np.array(
            [np.datetime64(f"{y:04d}-{m:02d}-01T00:00:00", "ns") for y, m in stamps]
        )
        data = np.array(
            [[[self.value_fn(y, m, la, lo) for lo in lons] for la in lats] for y, m in stamps],
            dtype="float32",
        )
        dataset = xr.Dataset(
            {self.var: (["valid_time", "latitude", "longitude"], data, {"units": self.units})},
            coords={"valid_time": times, "latitude": lats, "longitude": lons},
        )
        dataset.to_netcdf(target)


class FakeDownloader:
    def __init__(self, builder):
        self.builder = builder
        self.calls: list[tuple[str, dict]] = []

    def download(self, dataset, request, target):
        self.calls.append((dataset, dict(request)))
        self.builder(request, Path(target))