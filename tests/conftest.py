"""Shared fixtures. All rasters here are SYNTHETIC; no test touches the network."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import httpx
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from climateadapt.data.chirps import ChirpsMonthlyStore

WEST, NORTH, RES, WIDTH, HEIGHT = -10.0, 31.0, 0.05, 40, 40
BASE_URL = "https://example.test/products/CHIRPS/v3.0"


@pytest.fixture
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def today() -> date:
    return date(2026, 10, 24)


@pytest.fixture
def cell_center() -> Callable[[int, int], tuple[float, float]]:
    """(row, col) -> (lat, lon) of that cell's centre in the synthetic grid."""

    def _center(row: int, col: int) -> tuple[float, float]:
        return NORTH - (row + 0.5) * RES, WEST + (col + 0.5) * RES

    return _center


@pytest.fixture
def tif_factory(tmp_path) -> Callable[..., bytes]:
    """Build synthetic GeoTIFF bytes. Cell (r, c) holds r*100 + c + offset (float32).

    ``overrides`` maps (row, col) -> value, e.g. to inject nodata, NaN, or negatives.
    """
    folder = tmp_path / "synthetic"
    folder.mkdir()
    counter = {"n": 0}

    def make(
        *,
        offset: float = 0.0,
        overrides: dict[tuple[int, int], float] | None = None,
        nodata: float = -9999.0,
        declare_nodata: bool = True,
        west: float = WEST,
    ) -> bytes:
        counter["n"] += 1
        path = folder / f"synthetic_{counter['n']}.tif"
        rows, cols = np.indices((HEIGHT, WIDTH))
        data = (rows * 100 + cols + offset).astype("float32")
        for (r, c), value in (overrides or {}).items():
            data[r, c] = value
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=HEIGHT,
            width=WIDTH,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(west, NORTH, RES, RES),
            nodata=nodata if declare_nodata else None,
        ) as dst:
            dst.write(data, 1)
        return path.read_bytes()

    return make


@pytest.fixture
def http_mock():
    """Build (client, calls) from a {filename: bytes | callable -> Response} route table."""

    def build(routes: dict):
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            route = routes.get(request.url.path.rsplit("/", 1)[-1])
            if route is None:
                return httpx.Response(404)
            if callable(route):
                return route()
            return httpx.Response(200, content=route)

        return httpx.Client(transport=httpx.MockTransport(handler)), calls

    return build


@pytest.fixture
def make_store(tmp_path, today, base_url):
    def build(client: httpx.Client, **kwargs) -> ChirpsMonthlyStore:
        return ChirpsMonthlyStore(
            base_url=base_url,
            cache_dir=tmp_path / "cache",
            http_client=client,
            today=lambda: today,
            **kwargs,
        )

    return build