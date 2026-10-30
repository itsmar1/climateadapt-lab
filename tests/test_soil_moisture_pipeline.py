"""Offline tests for the ERA5-Land soil-moisture anomaly pipeline. No CDS or network."""

from __future__ import annotations

import pytest

from climateadapt.data.era5_land import Era5LandClient, Era5LandMonthlyStore
from climateadapt.data.errors import (
    DataIntegrityError,
    DataNotAvailableError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.soil_moisture import compute_soil_moisture_anomaly
from climateadapt.indicators.spi import InsufficientReferenceError
from climateadapt.pipelines.soil_moisture_anomaly import era5_land_soil_moisture_anomaly
from era5_helpers import LAT, LON, Builder, FakeDownloader

LAYER_1 = "volumetric_soil_water_layer_1"


def sw(year, month):
    """Deterministic synthetic soil water in m3/m3 (always inside [0, 1])."""
    return 0.15 + 0.005 * ((year * 12 + month) % 10)


def make_builder(nan_if=None, var="swvl1", units="m**3 m**-3"):
    def value_fn(year, month, lat, lon):
        if nan_if is not None and nan_if(year, month, lat, lon):
            return float("nan")
        return sw(year, month)

    return Builder(value_fn, var=var, units=units)


def mask_nearest_and_west(year, month, lat, lon):
    return lon == -9.7 or (lat == 30.4 and lon == -9.6)


@pytest.fixture
def make_client(tmp_path, today):
    def build(builder):
        downloader = FakeDownloader(builder)
        store = Era5LandMonthlyStore(
            cache_dir=tmp_path / "era5", downloader=downloader, today=lambda: today
        )
        return Era5LandClient(store), downloader

    return build


def params(**overrides):
    base = {
        "variable": LAYER_1,
        "latitude": LAT,
        "longitude": LON,
        "target_end_month": YearMonth(2024, 3),
        "timescale_months": 1,
    }
    base.update(overrides)
    return base


def test_single_month_anomaly_matches_the_pure_calculation(make_client):
    client, downloader = make_client(make_builder())

    result = era5_land_soil_moisture_anomaly(client, **params())

    monthly = {YearMonth(y, 3): sw(y, 3) for y in [*range(1991, 2021), 2024]}
    expected = compute_soil_moisture_anomaly(monthly, YearMonth(2024, 3), 1, 1991, 2020)
    assert result.window_mean_m3m3 == pytest.approx(expected.window_mean_m3m3, abs=1e-3)
    assert result.reference_mean_m3m3 == pytest.approx(expected.reference_mean_m3m3, abs=1e-3)
    assert result.anomaly_m3m3 == pytest.approx(expected.anomaly_m3m3, abs=1e-3)
    assert result.reference_sd_m3m3 == pytest.approx(expected.reference_sd_m3m3, abs=1e-3)
    assert result.standardized_anomaly == pytest.approx(
        expected.standardized_anomaly, abs=2e-3
    )
    assert result.percentile_rank == pytest.approx(expected.percentile_rank)
    assert result.indicator == "soil_moisture_window_anomaly"
    assert result.variable == LAYER_1
    assert result.layer_depth == "0-7 cm"
    assert result.reference_years_used == 30
    assert result.land_fallback is None
    assert (result.grid_point_latitude, result.grid_point_longitude) == (30.4, -9.6)
    assert "cds.68d2bb30" in result.doi
    assert any("not crop-water stress by itself" in t for t in result.limitations)
    assert any("only the anomaly" in t for t in result.limitations)
    dumped = result.model_dump()
    assert "severity" not in dumped and "category" not in dumped

    # One small request for the target, one grouped request for the 30 reference years.
    assert len(downloader.calls) == 2
    assert downloader.calls[1][1]["variable"] == [LAYER_1]
    assert downloader.calls[1][1]["year"] == [f"{y:04d}" for y in range(1991, 2021)]


def test_three_month_window_uses_day_weighted_means(make_client):
    client, _ = make_client(make_builder())

    result = era5_land_soil_moisture_anomaly(client, **params(timescale_months=3))

    monthly = {YearMonth(y, m): sw(y, m) for y in [*range(1991, 2021), 2024] for m in (1, 2, 3)}
    expected = compute_soil_moisture_anomaly(monthly, YearMonth(2024, 3), 3, 1991, 2020)
    assert result.target_window_start == "2024-01"
    assert result.window_mean_m3m3 == pytest.approx(expected.window_mean_m3m3, abs=1e-3)
    assert result.anomaly_m3m3 == pytest.approx(expected.anomaly_m3m3, abs=1e-3)


@pytest.mark.parametrize(
    ("variable", "var", "depth"),
    [
        ("volumetric_soil_water_layer_1", "swvl1", "0-7 cm"),
        ("volumetric_soil_water_layer_2", "swvl2", "7-28 cm"),
        ("volumetric_soil_water_layer_3", "swvl3", "28-100 cm"),
    ],
)
def test_all_three_layers_run_with_their_depths(make_client, variable, var, depth):
    client, downloader = make_client(make_builder(var=var))

    result = era5_land_soil_moisture_anomaly(client, **params(variable=variable))

    assert result.variable == variable
    assert result.layer_depth == depth
    assert result.reference_years_used == 30
    assert downloader.calls[1][1]["variable"] == [variable]


def test_masked_nearest_point_needs_the_opt_in_fallback(make_client):
    client, _ = make_client(make_builder(nan_if=mask_nearest_and_west))

    with pytest.raises(MissingDataError, match="land_fallback_max_km"):
        era5_land_soil_moisture_anomaly(client, **params())

    result = era5_land_soil_moisture_anomaly(client, **params(), land_fallback_max_km=15.0)

    assert result.land_fallback.used is True
    assert (result.grid_point_latitude, result.grid_point_longitude) == (30.5, -9.6)
    assert "neighbouring grid point" in result.limitations[0]


def test_a_different_neighbour_in_some_years_is_refused(make_client):
    def mask(year, month, lat, lon):
        return mask_nearest_and_west(year, month, lat, lon) or (
            year == 2005 and (lat, lon) == (30.5, -9.6)
        )

    client, _ = make_client(make_builder(nan_if=mask))
    with pytest.raises(DataIntegrityError, match="Grid point differs"):
        era5_land_soil_moisture_anomaly(client, **params(), land_fallback_max_km=15.0)


def test_too_many_missing_reference_years_raise(make_client):
    client, _ = make_client(make_builder(nan_if=lambda y, m, la, lo: y in (1995, 1996, 1997, 1998)))
    with pytest.raises(InsufficientReferenceError, match="Only 26 of 30"):
        era5_land_soil_moisture_anomaly(client, **params())


def test_missing_reference_years_are_reported_when_the_minimum_allows(make_client):
    client, _ = make_client(make_builder(nan_if=lambda y, m, la, lo: y in (1995, 1996)))

    result = era5_land_soil_moisture_anomaly(client, **params(), min_reference_years=20)

    assert result.reference_years_used == 28
    assert [e.year for e in result.reference_years_excluded] == [1995, 1996]
    assert any("excluded" in text for text in result.limitations)


def test_short_reference_and_target_inside_reference_are_flagged(make_client):
    client, _ = make_client(make_builder())

    result = era5_land_soil_moisture_anomaly(
        client,
        **params(target_end_month=YearMonth(2020, 3), reference_start_year=2001),
        min_reference_years=20,
    )

    assert result.reference_years_used == 20
    assert result.target_in_reference_period is True
    assert any("only 20 usable years" in text for text in result.limitations)
    assert any("contributed to its own reference mean" in text for text in result.limitations)


def test_wrong_file_units_are_rejected(make_client):
    client, _ = make_client(make_builder(units="kg m-2"))
    with pytest.raises(DataIntegrityError, match="units"):
        era5_land_soil_moisture_anomaly(client, **params())


@pytest.mark.parametrize(
    ("overrides", "extra", "error"),
    [
        ({"target_end_month": YearMonth(2026, 10)}, {}, DataNotAvailableError),
        ({"reference_end_year": 2027}, {}, DataNotAvailableError),
        ({"target_end_month": YearMonth(1949, 12)}, {}, OutsideCoverageError),
        ({"latitude": -90.0, "longitude": 0.0}, {}, OutsideCoverageError),
        ({"timescale_months": 0}, {}, ValueError),
        ({"reference_start_year": 2020, "reference_end_year": 1991}, {}, ValueError),
        ({"variable": "2m_temperature"}, {}, ValueError),
        ({"variable": "volumetric_soil_water_layer_4"}, {}, ValueError),
        ({}, {"land_fallback_max_km": 99.0}, ValueError),
    ],
)
def test_invalid_requests_make_no_cds_requests(make_client, overrides, extra, error):
    client, downloader = make_client(make_builder())
    with pytest.raises(error):
        era5_land_soil_moisture_anomaly(client, **params(**overrides), **extra)
    assert downloader.calls == []
