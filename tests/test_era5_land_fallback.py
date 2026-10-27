"""Offline tests for the ERA5-Land nearest-land fallback. No CDS access or network."""

from __future__ import annotations

import json
import math

import pytest

from climateadapt.data.era5_land import (
    Era5LandClient,
    Era5LandMonthlyStore,
    total_precipitation_mm,
)
from climateadapt.data.periods import YearMonth
from climateadapt.geo import haversine_km
from climateadapt.indicators.units import days_in_month
from era5_helpers import LAT, LON, Builder, FakeDownloader, cell_value

JAN, FEB, MAR = YearMonth(2024, 1), YearMonth(2024, 2), YearMonth(2024, 3)
VAR = "total_precipitation"
NAN = float("nan")


def precip_builder(value_fn):
    return Builder(value_fn, var="tp", units="m")


def masked_west_and_centre(year, month, lat, lon):
    """Nearest point (30.4, -9.6) and the whole -9.7 column are masked."""
    if lon == -9.7 or (lat == 30.4 and lon == -9.6):
        return NAN
    return cell_value(year, month, lat, lon)


@pytest.fixture
def make_client(tmp_path, today):
    def build(builder):
        downloader = FakeDownloader(builder)
        store = Era5LandMonthlyStore(
            cache_dir=tmp_path / "era5", downloader=downloader, today=lambda: today
        )
        return Era5LandClient(store), downloader

    return build


def expected_mm(lat, lon):
    return [
        cell_value(2024, m, lat, lon) * 1000 * days_in_month(2024, m) for m in (1, 2, 3)
    ]


def test_default_is_strict_and_reports_missing(make_client):
    client, _ = make_client(precip_builder(masked_west_and_centre))
    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR)

    assert series.land_fallback is None
    assert all(v.value is None for v in series.values)
    assert (series.grid_point_latitude, series.grid_point_longitude) == (30.4, -9.6)


def test_fallback_selects_the_nearest_valid_neighbour_and_says_so(make_client):
    client, _ = make_client(precip_builder(masked_west_and_centre))
    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=15.0)

    info = series.land_fallback
    assert info is not None
    assert info.used is True
    assert (info.nearest_grid_point_latitude, info.nearest_grid_point_longitude) == (30.4, -9.6)
    assert (info.selected_grid_point_latitude, info.selected_grid_point_longitude) == (30.5, -9.6)
    assert info.distance_km == pytest.approx(haversine_km(LAT, LON, 30.5, -9.6))
    assert 7.0 < info.distance_km < 8.5
    assert (series.grid_point_latitude, series.grid_point_longitude) == (30.5, -9.6)

    expected = expected_mm(30.5, -9.6)
    assert [v.value for v in series.values] == pytest.approx(expected, abs=1e-3)
    assert all(v.status == "ok" and v.notes for v in series.values)
    assert "neighbouring grid point" in series.limitations[0]
    assert total_precipitation_mm(series) == pytest.approx(sum(expected), abs=1e-2)


@pytest.mark.parametrize(("max_km", "expect_used"), [(7.0, False), (8.5, True)])
def test_fallback_respects_the_maximum_distance(make_client, max_km, expect_used):
    client, _ = make_client(precip_builder(masked_west_and_centre))
    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=max_km)

    info = series.land_fallback
    assert info.used is expect_used
    if expect_used:
        assert info.distance_km <= max_km
    else:
        assert info.selected_grid_point_latitude is None
        assert info.distance_km is None
        assert "7 km" in info.reason
        assert all(v.value is None for v in series.values)
        assert (series.grid_point_latitude, series.grid_point_longitude) == (30.4, -9.6)
        assert not any("neighbouring" in text for text in series.limitations)


def test_fallback_not_used_when_the_nearest_point_has_data(make_client):
    client, _ = make_client(precip_builder(cell_value))
    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=15.0)

    assert series.land_fallback.used is False
    assert "has data" in series.land_fallback.reason
    assert (series.grid_point_latitude, series.grid_point_longitude) == (30.4, -9.6)
    assert all(v.value is not None for v in series.values)


def test_fallback_not_used_when_only_some_months_are_missing(make_client):
    def gap_in_february(year, month, lat, lon):
        if (lat, lon) == (30.4, -9.6) and month == 2:
            return NAN
        return cell_value(year, month, lat, lon)

    client, _ = make_client(precip_builder(gap_in_february))
    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=15.0)

    assert series.land_fallback.used is False
    assert "some months" in series.land_fallback.reason
    assert [v.value is None for v in series.values] == [False, True, False]


def test_fallback_not_used_when_every_neighbour_is_masked(make_client):
    client, _ = make_client(precip_builder(lambda y, m, la, lo: NAN))
    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=25.0)

    assert series.land_fallback.used is False
    assert "No neighbouring grid point" in series.land_fallback.reason
    assert all(v.value is None for v in series.values)


def test_neighbour_with_a_gap_in_any_month_is_skipped(make_client):
    def best_neighbour_has_a_gap(year, month, lat, lon):
        if lon == -9.7 or (lat == 30.4 and lon == -9.6):
            return NAN
        if (lat, lon) == (30.5, -9.6) and month == 3:
            return NAN
        return cell_value(year, month, lat, lon)

    client, _ = make_client(precip_builder(best_neighbour_has_a_gap))
    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=15.0)

    info = series.land_fallback
    assert info.used is True
    assert (info.selected_grid_point_latitude, info.selected_grid_point_longitude) == (30.4, -9.5)
    assert [v.value for v in series.values] == pytest.approx(expected_mm(30.4, -9.5), abs=1e-3)


def test_fallback_applies_unit_conversion_for_temperature(make_client):
    def temp_cell(year, month, lat, lon):
        if lon == -9.7 or (lat == 30.4 and lon == -9.6):
            return NAN
        return 280.0 + month + round((lat - 30.0) * 10)

    client, _ = make_client(Builder(temp_cell, var="t2m", units="K"))
    series = client.monthly_point_series(
        "2m_temperature", LAT, LON, JAN, FEB, land_fallback_max_km=15.0
    )

    assert series.units == "degC"
    assert series.land_fallback.used is True
    # Neighbour (30.5, -9.6): 280 + month + 5 K
    assert [v.value for v in series.values] == pytest.approx([12.85, 13.85], abs=1e-3)


@pytest.mark.parametrize("bad", [0, -1.0, math.nan, math.inf, True, "5", 25.5])
def test_invalid_fallback_distance_is_rejected_before_any_request(make_client, bad):
    client, downloader = make_client(precip_builder(masked_west_and_centre))
    with pytest.raises(ValueError, match="land_fallback_max_km"):
        client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=bad)
    assert downloader.calls == []


def test_fallback_decision_is_made_from_the_cache_without_new_downloads(make_client):
    client, downloader = make_client(precip_builder(masked_west_and_centre))
    client.monthly_point_series(VAR, LAT, LON, JAN, MAR)
    assert len(downloader.calls) == 1

    series = client.monthly_point_series(VAR, LAT, LON, JAN, MAR, land_fallback_max_km=15.0)

    assert len(downloader.calls) == 1
    assert series.land_fallback.used is True


def _record_path(client):
    return (
        client.store.cache_dir
        / "monthly"
        / VAR
        / "lat30.4300_lon-9.6100"
        / "2024-01.json"
    )


def test_records_store_the_surrounding_grid_points(make_client):
    client, _ = make_client(precip_builder(masked_west_and_centre))
    client.monthly_point_series(VAR, LAT, LON, JAN, JAN)

    data = json.loads(_record_path(client).read_text(encoding="utf-8"))
    neighbours = {(n["latitude"], n["longitude"]): n["raw_value"] for n in data["neighbours"]}

    assert len(neighbours) == 8
    assert (30.4, -9.6) not in neighbours  # the nearest point itself is not a neighbour
    assert neighbours[(30.5, -9.7)] is None
    assert neighbours[(30.5, -9.6)] == pytest.approx(cell_value(2024, 1, 30.5, -9.6), rel=1e-5)


def test_cached_record_without_neighbours_is_redownloaded(make_client):
    client, downloader = make_client(precip_builder(masked_west_and_centre))
    client.monthly_point_series(VAR, LAT, LON, JAN, JAN)
    assert len(downloader.calls) == 1

    path = _record_path(client)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["neighbours"]  # simulate a record written by an older version
    path.write_text(json.dumps(data), encoding="utf-8")

    client.monthly_point_series(VAR, LAT, LON, JAN, JAN)

    assert len(downloader.calls) == 2
    assert "neighbours" in json.loads(path.read_text(encoding="utf-8"))