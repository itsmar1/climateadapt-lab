import hashlib
import math

import httpx
import pytest

from climateadapt.config import Settings
from climateadapt.data.chirps import (
    ChirpsV3Client,
    accumulated_total_mm,
    build_chirps_client,
    monthly_filename,
    sample_point,
)
from climateadapt.data.errors import (
    DataIntegrityError,
    DataNotAvailableError,
    DownloadError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.data.periods import YearMonth

MARCH = YearMonth(2024, 3)
MARCH_FILE = "chirps-v3.0.2024.03.tif"


def test_monthly_filename():
    assert monthly_filename(MARCH) == MARCH_FILE


# ---------------------------------------------------------------- store: download/cache


def test_download_then_cache_hit(tif_factory, http_mock, make_store, base_url):
    tif = tif_factory()
    client, calls = http_mock({MARCH_FILE: tif})
    store = make_store(client)

    path, prov = store.ensure_cached(MARCH)

    assert path.read_bytes() == tif
    assert prov.sha256 == hashlib.sha256(tif).hexdigest()
    assert prov.size_bytes == len(tif)
    assert prov.source_url == f"{base_url}/monthly/global/tifs/{MARCH_FILE}"
    assert prov.units == "mm/month"
    assert prov.product == "final"
    assert "G2JQ0P" in prov.doi
    assert path.with_suffix(".provenance.json").exists()
    assert len(calls) == 1

    path2, prov2 = store.ensure_cached(MARCH)
    assert path2 == path
    assert prov2 == prov
    assert len(calls) == 1  # served from cache


def test_missing_file_is_not_available_and_leaves_no_files(tmp_path, http_mock, make_store):
    client, _ = http_mock({})
    with pytest.raises(DataNotAvailableError, match="not be published yet"):
        make_store(client).ensure_cached(MARCH)
    assert list((tmp_path / "cache").iterdir()) == []


def test_http_500_is_download_error(http_mock, make_store):
    client, _ = http_mock({MARCH_FILE: lambda: httpx.Response(500)})
    with pytest.raises(DownloadError, match="500"):
        make_store(client).ensure_cached(MARCH)


def test_network_failure_is_download_error(http_mock, make_store):
    def boom():
        raise httpx.ConnectError("no route to host")

    client, _ = http_mock({MARCH_FILE: boom})
    with pytest.raises(DownloadError, match="Network failure"):
        make_store(client).ensure_cached(MARCH)


def test_html_page_instead_of_raster_is_rejected_and_not_cached(
    tmp_path, http_mock, make_store
):
    client, _ = http_mock({MARCH_FILE: b"<html>Service unavailable</html>"})
    with pytest.raises(DataIntegrityError, match="not a readable raster"):
        make_store(client).ensure_cached(MARCH)
    assert list((tmp_path / "cache").iterdir()) == []


def test_content_length_mismatch_is_rejected(tmp_path, tif_factory, http_mock, make_store):
    tif = tif_factory()

    def wrong_length():
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(tif) + 1)},
            stream=httpx.ByteStream(tif),
        )

    client, _ = http_mock({MARCH_FILE: wrong_length})
    with pytest.raises(DataIntegrityError, match="size"):
        make_store(client).ensure_cached(MARCH)
    assert list((tmp_path / "cache").iterdir()) == []


def test_tampered_cache_is_redownloaded(tif_factory, http_mock, make_store):
    tif = tif_factory()
    client, calls = http_mock({MARCH_FILE: tif})
    store = make_store(client)
    path, _ = store.ensure_cached(MARCH)

    path.write_bytes(path.read_bytes() + b"x")  # size no longer matches provenance
    path2, _ = store.ensure_cached(MARCH)

    assert len(calls) == 2
    assert path2.read_bytes() == tif


def test_missing_sidecar_triggers_redownload(tif_factory, http_mock, make_store):
    client, calls = http_mock({MARCH_FILE: tif_factory()})
    store = make_store(client)
    path, _ = store.ensure_cached(MARCH)

    path.with_suffix(".provenance.json").unlink()
    store.ensure_cached(MARCH)

    assert len(calls) == 2


def test_offline_mode_without_cache_fails_without_network(http_mock, make_store):
    client, calls = http_mock({MARCH_FILE: b"unused"})
    with pytest.raises(DataNotAvailableError, match="downloads are disabled"):
        make_store(client, allow_downloads=False).ensure_cached(MARCH)
    assert calls == []


def test_offline_mode_uses_existing_cache(tif_factory, http_mock, make_store):
    client, _ = http_mock({MARCH_FILE: tif_factory()})
    make_store(client).ensure_cached(MARCH)

    offline_client, calls = http_mock({})
    path, prov = make_store(offline_client, allow_downloads=False).ensure_cached(MARCH)

    assert path.exists()
    assert prov.year == 2024
    assert calls == []


def test_current_month_rejected_before_any_request(http_mock, make_store):
    client, calls = http_mock({})
    with pytest.raises(DataNotAvailableError, match="not ended"):
        make_store(client).ensure_cached(YearMonth(2026, 10))
    assert calls == []


# ---------------------------------------------------------------- point sampling


def test_sample_exact_cell(tmp_path, tif_factory, cell_center):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory())
    lat, lon = cell_center(5, 7)

    sample = sample_point(path, lat, lon)

    assert (sample.row, sample.col) == (5, 7)
    assert sample.value_mm == 507.0
    assert sample.pixel_center_latitude == pytest.approx(lat)
    assert sample.pixel_center_longitude == pytest.approx(lon)


def test_off_centre_point_maps_to_same_cell(tmp_path, tif_factory, cell_center):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory())
    lat, lon = cell_center(5, 7)

    sample = sample_point(path, lat + 0.02, lon - 0.02)

    assert (sample.row, sample.col) == (5, 7)
    assert sample.value_mm == 507.0


def test_point_outside_raster_extent(tmp_path, tif_factory):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory())
    with pytest.raises(OutsideCoverageError, match="raster extent"):
        sample_point(path, 40.0, 0.0)


@pytest.mark.parametrize("declare_nodata", [True, False])
def test_nodata_sentinel_becomes_none(tmp_path, tif_factory, cell_center, declare_nodata):
    path = tmp_path / "s.tif"
    path.write_bytes(
        tif_factory(overrides={(2, 3): -9999.0}, declare_nodata=declare_nodata)
    )
    sample = sample_point(path, *cell_center(2, 3))
    assert sample.value_mm is None


def test_nan_becomes_none(tmp_path, tif_factory, cell_center):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory(overrides={(0, 1): float("nan")}))
    assert sample_point(path, *cell_center(0, 1)).value_mm is None


def test_zero_rainfall_is_a_valid_value_not_missing(tmp_path, tif_factory, cell_center):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory(overrides={(1, 1): 0.0}))
    assert sample_point(path, *cell_center(1, 1)).value_mm == 0.0


def test_unexpected_negative_value_is_integrity_error(tmp_path, tif_factory, cell_center):
    path = tmp_path / "s.tif"
    path.write_bytes(tif_factory(overrides={(4, 4): -5.0}))
    with pytest.raises(DataIntegrityError, match="negative"):
        sample_point(path, *cell_center(4, 4))


# ---------------------------------------------------------------- series


def _client_for(make_store, http_mock, routes):
    http, calls = http_mock(routes)
    return ChirpsV3Client(make_store(http)), calls


def test_three_month_series_and_total(tif_factory, http_mock, make_store, cell_center):
    routes = {f"chirps-v3.0.2024.0{m}.tif": tif_factory(offset=m * 1000.0) for m in (1, 2, 3)}
    client, calls = _client_for(make_store, http_mock, routes)
    lat, lon = cell_center(5, 7)

    series = client.monthly_point_series(lat, lon, YearMonth(2024, 1), YearMonth(2024, 3))

    assert [v.precipitation_mm for v in series.values] == [1507.0, 2507.0, 3507.0]
    assert all(v.status == "ok" for v in series.values)
    assert len(series.provenance) == 3
    assert len(calls) == 3
    assert accumulated_total_mm(series) == pytest.approx(7521.0)
    assert series.units == "mm/month"
    assert series.product == "final"
    assert series.limitations
    assert series.pixel_center_latitude == pytest.approx(lat)


def test_missing_month_blocks_total(tif_factory, http_mock, make_store, cell_center):
    routes = {
        "chirps-v3.0.2024.01.tif": tif_factory(offset=1000.0),
        "chirps-v3.0.2024.02.tif": tif_factory(offset=2000.0, overrides={(5, 7): -9999.0}),
    }
    client, _ = _client_for(make_store, http_mock, routes)

    series = client.monthly_point_series(
        *cell_center(5, 7), YearMonth(2024, 1), YearMonth(2024, 2)
    )

    assert series.values[1].precipitation_mm is None
    assert series.values[1].status == "missing_value"
    with pytest.raises(MissingDataError, match="2024-02"):
        accumulated_total_mm(series)


def test_out_of_coverage_point_makes_no_requests(http_mock, make_store):
    client, calls = _client_for(make_store, http_mock, {})
    with pytest.raises(OutsideCoverageError):
        client.monthly_point_series(70.0, 10.0, YearMonth(2024, 1), YearMonth(2024, 3))
    assert calls == []


def test_unavailable_month_in_range_makes_no_requests(http_mock, make_store):
    client, calls = _client_for(make_store, http_mock, {})
    with pytest.raises(DataNotAvailableError):
        client.monthly_point_series(30.4, -9.6, YearMonth(2026, 8), YearMonth(2026, 10))
    assert calls == []


def test_reversed_range_rejected(http_mock, make_store):
    client, calls = _client_for(make_store, http_mock, {})
    with pytest.raises(ValueError):
        client.monthly_point_series(30.4, -9.6, YearMonth(2024, 3), YearMonth(2024, 1))
    assert calls == []


def test_invalid_coordinates_rejected(http_mock, make_store):
    client, calls = _client_for(make_store, http_mock, {})
    with pytest.raises(ValueError):
        client.monthly_point_series(float("nan"), -9.6, YearMonth(2024, 1), YearMonth(2024, 1))
    assert calls == []


def test_inconsistent_grid_between_months_is_rejected(
    tif_factory, http_mock, make_store, cell_center
):
    routes = {
        "chirps-v3.0.2024.01.tif": tif_factory(),
        "chirps-v3.0.2024.02.tif": tif_factory(west=-10.05),  # shifted by one cell
    }
    client, _ = _client_for(make_store, http_mock, routes)
    with pytest.raises(DataIntegrityError, match="Grid geometry"):
        client.monthly_point_series(
            *cell_center(5, 7), YearMonth(2024, 1), YearMonth(2024, 2)
        )


def test_accumulated_total_of_empty_series_raises(tif_factory, http_mock, make_store, cell_center):
    routes = {"chirps-v3.0.2024.01.tif": tif_factory()}
    client, _ = _client_for(make_store, http_mock, routes)
    series = client.monthly_point_series(
        *cell_center(1, 1), YearMonth(2024, 1), YearMonth(2024, 1)
    )
    assert math.isfinite(accumulated_total_mm(series))
    empty = series.model_copy(update={"values": []})
    with pytest.raises(ValueError):
        accumulated_total_mm(empty)


def test_build_client_uses_configured_data_dir(tmp_path):
    client = build_chirps_client(Settings(data_dir=tmp_path))
    try:
        assert tmp_path in client.store.cache_dir.parents
    finally:
        client.store.close()