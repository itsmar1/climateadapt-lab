"""Offline tests for the CHIRPS remote single-pixel store: no network, synthetic rasters."""

from __future__ import annotations

from contextlib import contextmanager

import httpx
import pytest
import rasterio
from rasterio.errors import RasterioIOError

from climateadapt.config import Settings
from climateadapt.data.chirps import (
    ChirpsMonthlyStore,
    ChirpsV3Client,
    accumulated_total_mm,
    build_chirps_client,
)
from climateadapt.data.chirps_remote import ChirpsRemoteStore
from climateadapt.data.errors import DataNotAvailableError, DownloadError
from climateadapt.data.periods import YearMonth
from climateadapt.pipelines.rainfall_anomaly import chirps_rainfall_anomaly

FILE = "chirps-v3.0.2024.03.tif"
MARCH = YearMonth(2024, 3)


@pytest.fixture
def remote(tmp_path, today, base_url, http_mock):
    """Build (store, opened_urls, http_calls) from {filename: tif_bytes}."""

    def build(files, *, head_routes=None, allow_downloads=True, max_workers=4):
        folder = tmp_path / "remote_files"
        folder.mkdir(exist_ok=True)
        paths = {}
        for name, data in files.items():
            target = folder / name
            target.write_bytes(data)
            paths[name] = target
        opened: list[str] = []

        @contextmanager
        def opener(url):
            opened.append(url)
            name = url.rsplit("/", 1)[-1]
            if name not in paths:
                raise RasterioIOError(f"{name} is not readable")
            with rasterio.open(paths[name]) as src:
                yield src

        if head_routes is None:
            head_routes = {name: (lambda: httpx.Response(200)) for name in files}
        http, http_calls = http_mock(head_routes)
        store = ChirpsRemoteStore(
            base_url=base_url,
            cache_dir=tmp_path / "remote_cache",
            http_client=http,
            opener=opener,
            allow_downloads=allow_downloads,
            max_workers=max_workers,
            today=lambda: today,
        )
        return store, opened, http_calls

    return build


def test_read_returns_value_and_remote_provenance(remote, tif_factory, cell_center, base_url):
    head = {
        FILE: lambda: httpx.Response(
            200,
            headers={
                "ETag": '"abc123"',
                "Last-Modified": "Wed, 04 Dec 2024 14:18:26 GMT",
                "Content-Length": "12345",
            },
        )
    }
    store, opened, _ = remote({FILE: tif_factory()}, head_routes=head)

    reading = store.read_point(MARCH, *cell_center(5, 7))

    assert reading.sample.value_mm == 507.0
    assert (reading.sample.row, reading.sample.col) == (5, 7)
    prov = reading.provenance
    assert prov.access_mode == "remote_range_read"
    assert prov.remote_etag == '"abc123"'
    assert prov.remote_last_modified == "Wed, 04 Dec 2024 14:18:26 GMT"
    assert prov.size_bytes == 12345
    assert prov.sha256 is None
    assert prov.cache_path is None
    assert prov.source_url == f"{base_url}/monthly/global/tifs/{FILE}"
    assert opened == [prov.source_url]


def test_second_read_is_served_from_cache(remote, tif_factory, cell_center):
    store, opened, http_calls = remote({FILE: tif_factory()})
    lat, lon = cell_center(5, 7)

    first = store.read_point(MARCH, lat, lon)
    second = store.read_point(MARCH, lat, lon)

    assert len(opened) == 1
    assert len(http_calls) == 1
    assert second.sample == first.sample
    assert second.provenance == first.provenance


def test_cache_persists_and_offline_mode_uses_it(remote, tif_factory, cell_center):
    files = {FILE: tif_factory()}
    store, _, _ = remote(files)
    lat, lon = cell_center(5, 7)
    store.read_point(MARCH, lat, lon)

    offline, opened, http_calls = remote(files, allow_downloads=False)

    assert offline.read_point(MARCH, lat, lon).sample.value_mm == 507.0
    with pytest.raises(DataNotAvailableError, match="downloads are disabled"):
        offline.read_point(YearMonth(2024, 4), lat, lon)
    assert opened == []
    assert http_calls == []


def test_head_404_means_not_published(remote):
    store, opened, _ = remote({}, head_routes={})
    with pytest.raises(DataNotAvailableError, match="not be published yet"):
        store.read_point(MARCH, 30.0, -9.0)
    assert opened == []


def test_head_failure_status_only_loses_metadata(remote, tif_factory, cell_center):
    store, _, _ = remote(
        {FILE: tif_factory()}, head_routes={FILE: lambda: httpx.Response(500)}
    )

    reading = store.read_point(MARCH, *cell_center(5, 7))

    assert reading.sample.value_mm == 507.0
    assert reading.provenance.remote_etag is None
    assert reading.provenance.size_bytes is None


def test_head_network_error_is_download_error(remote):
    def boom():
        raise httpx.ConnectError("no route to host")

    store, opened, _ = remote({}, head_routes={FILE: boom})
    with pytest.raises(DownloadError, match="Network failure"):
        store.read_point(MARCH, 30.0, -9.0)
    assert opened == []


def test_unreadable_remote_raster_is_download_error(remote):
    store, _, _ = remote({}, head_routes={FILE: lambda: httpx.Response(200)})
    with pytest.raises(DownloadError, match="Remote read"):
        store.read_point(MARCH, 30.0, -9.0)


def test_unavailable_month_makes_no_requests(remote, tif_factory):
    store, opened, http_calls = remote({FILE: tif_factory()})
    with pytest.raises(DataNotAvailableError):
        store.read_point(YearMonth(2026, 10), 30.0, -9.0)
    assert opened == []
    assert http_calls == []


def test_nodata_is_cached_as_missing(remote, tif_factory, cell_center):
    store, opened, _ = remote({FILE: tif_factory(overrides={(5, 7): -9999.0})})
    lat, lon = cell_center(5, 7)

    assert store.read_point(MARCH, lat, lon).sample.value_mm is None
    assert store.read_point(MARCH, lat, lon).sample.value_mm is None
    assert len(opened) == 1


def test_prefetch_reads_in_parallel_then_serves_from_cache(remote, tif_factory, cell_center):
    files = {f"chirps-v3.0.2024.0{m}.tif": tif_factory(offset=m * 1000.0) for m in (1, 2, 3)}
    store, opened, _ = remote(files)
    lat, lon = cell_center(5, 7)
    months = [YearMonth(2024, m) for m in (1, 2, 3)]

    store.prefetch(months, lat, lon)
    assert len(opened) == 3

    values = [store.read_point(month, lat, lon).sample.value_mm for month in months]
    assert values == [1507.0, 2507.0, 3507.0]
    assert len(opened) == 3


def test_prefetch_propagates_errors(remote, tif_factory, cell_center):
    files = {
        "chirps-v3.0.2024.01.tif": tif_factory(),
        "chirps-v3.0.2024.03.tif": tif_factory(),
    }
    heads = {f"chirps-v3.0.2024.0{m}.tif": (lambda: httpx.Response(200)) for m in (1, 2, 3)}
    store, _, _ = remote(files, head_routes=heads)
    months = [YearMonth(2024, m) for m in (1, 2, 3)]

    with pytest.raises(DownloadError, match="Remote read"):
        store.prefetch(months, *cell_center(5, 7))


def test_prefetch_fails_fast_on_unavailable_month(remote, tif_factory):
    store, opened, _ = remote({FILE: tif_factory()})
    with pytest.raises(DataNotAvailableError):
        store.prefetch([MARCH, YearMonth(2026, 10)], 30.0, -9.0)
    assert opened == []


def test_prefetch_offline_with_missing_cache_fails(remote, tif_factory):
    store, opened, _ = remote({FILE: tif_factory()}, allow_downloads=False)
    with pytest.raises(DataNotAvailableError, match="downloads are disabled"):
        store.prefetch([MARCH], 30.0, -9.0)
    assert opened == []


def test_client_series_and_total_work_with_remote_store(remote, tif_factory, cell_center):
    files = {f"chirps-v3.0.2024.0{m}.tif": tif_factory(offset=m * 1000.0) for m in (1, 2, 3)}
    store, _, _ = remote(files)

    series = ChirpsV3Client(store).monthly_point_series(
        *cell_center(5, 7), YearMonth(2024, 1), YearMonth(2024, 3)
    )

    assert [v.precipitation_mm for v in series.values] == [1507.0, 2507.0, 3507.0]
    assert {p.access_mode for p in series.provenance} == {"remote_range_read"}
    assert accumulated_total_mm(series) == pytest.approx(7521.0)


def test_pipeline_runs_on_the_remote_store(remote, season_routes, cell_center):
    pairs = [(y, m) for y in range(2011, 2021) for m in (3, 4, 5)]
    pairs += [(2024, m) for m in (3, 4, 5)]
    files = season_routes(pairs, lambda y, m: 24.0 if y == 2024 else 30.0)
    store, opened, _ = remote(files)
    lat, lon = cell_center(5, 7)

    result = chirps_rainfall_anomaly(
        ChirpsV3Client(store),
        latitude=lat,
        longitude=lon,
        observed_start=YearMonth(2024, 3),
        window_months_count=3,
        baseline_start_year=2011,
        baseline_end_year=2020,
    )

    assert result.percentage_anomaly == pytest.approx(-20.0)
    assert len(result.source_files) == 33
    assert len(opened) == 33
    assert {f.access_mode for f in result.source_files} == {"remote_range_read"}
    assert all(f.sha256 is None for f in result.source_files)


def test_build_client_selects_the_access_mode(tmp_path):
    remote_client = build_chirps_client(Settings(data_dir=tmp_path, chirps_access="remote"))
    download_client = build_chirps_client(Settings(data_dir=tmp_path, chirps_access="download"))
    try:
        assert isinstance(remote_client.store, ChirpsRemoteStore)
        assert remote_client.store.cache_dir.name == "remote_points"
        assert isinstance(download_client.store, ChirpsMonthlyStore)
        assert download_client.store.cache_dir.name == "monthly_global"
    finally:
        remote_client.store.close()
        download_client.store.close()