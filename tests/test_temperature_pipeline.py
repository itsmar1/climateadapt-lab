"""Offline tests for the ERA5-Land temperature anomaly pipeline. No CDS access or network."""

from __future__ import annotations

import numpy as np
import pytest

from climateadapt.data.era5_land import Era5LandClient, Era5LandMonthlyStore
from climateadapt.data.errors import (
    DataIntegrityError,
    DataNotAvailableError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.spi import InsufficientReferenceError
from climateadapt.indicators.temperature import compute_temperature_anomaly
from climateadapt.pipelines.temperature_anomaly import era5_land_temperature_anomaly
from era5_helpers import LAT, LON, Builder, FakeDownloader

KELVIN = 273.15


def tc(year, month):
    """Synthetic monthly mean temperature (degC)."""
    return float(np.random.default_rng(year * 100 + month).normal(15.0, 1.5))


def make_builder(nan_if=None):
    def value_fn(year, month, lat, lon):
        if nan_if is not None and nan_if(year, month, lat, lon):
            return float("nan")
        return tc(year, month) + KELVIN

    return Builder(value_fn, var="t2m", units="K")


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
        "latitude": LAT,
        "longitude": LON,
        "target_end_month": YearMonth(2024, 3),
        "timescale_months": 1,
    }
    base.update(overrides)
    return base


def test_single_month_anomaly_matches_the_pure_calculation(make_client):
    client, downloader = make_client(make_builder())

    result = era5_land_temperature_anomaly(client, **params())

    monthly = {YearMonth(y, 3): tc(y, 3) for y in [*range(1991, 2021), 2024]}
    expected = compute_temperature_anomaly(monthly, YearMonth(2024, 3), 1, 1991, 2020)
    assert result.window_mean_c == pytest.approx(expected.window_mean_c, abs=1e-3)
    assert result.reference_mean_c == pytest.approx(expected.reference_mean_c, abs=1e-3)
    assert result.anomaly_c == pytest.approx(expected.anomaly_c, abs=1e-3)
    assert result.reference_sd_c == pytest.approx(expected.reference_sd_c, abs=1e-3)
    assert result.standardized_anomaly == pytest.approx(expected.standardized_anomaly, abs=2e-3)
    assert result.percentile_rank == pytest.approx(expected.percentile_rank)
    assert result.indicator == "temperature_window_anomaly"
    assert result.reference_years_used == 30
    assert result.land_fallback is None
    assert (result.grid_point_latitude, result.grid_point_longitude) == (30.4, -9.6)
    assert "cds.68d2bb30" in result.doi
    assert any("not a drought indicator by itself" in t for t in result.limitations)
    dumped = result.model_dump()
    assert "severity" not in dumped and "category" not in dumped

    # One small request for the target, one grouped request for the 30 reference years.
    assert len(downloader.calls) == 2
    assert downloader.calls[1][1]["variable"] == ["2m_temperature"]
    assert downloader.calls[1][1]["year"] == [f"{y:04d}" for y in range(1991, 2021)]


def test_three_month_window_uses_day_weighted_means(make_client):
    client, _ = make_client(make_builder())

    result = era5_land_temperature_anomaly(client, **params(timescale_months=3))

    monthly = {YearMonth(y, m): tc(y, m) for y in [*range(1991, 2021), 2024] for m in (1, 2, 3)}
    expected = compute_temperature_anomaly(monthly, YearMonth(2024, 3), 3, 1991, 2020)
    assert result.target_window_start == "2024-01"
    assert result.window_mean_c == pytest.approx(expected.window_mean_c, abs=1e-3)
    assert result.anomaly_c == pytest.approx(expected.anomaly_c, abs=1e-3)


def test_masked_nearest_point_needs_the_opt_in_fallback(make_client):
    client, _ = make_client(make_builder(nan_if=mask_nearest_and_west))

    with pytest.raises(MissingDataError, match="land_fallback_max_km"):
        era5_land_temperature_anomaly(client, **params())

    result = era5_land_temperature_anomaly(client, **params(), land_fallback_max_km=15.0)

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
        era5_land_temperature_anomaly(client, **params(), land_fallback_max_km=15.0)


def test_too_many_missing_reference_years_raise(make_client):
    client, _ = make_client(make_builder(nan_if=lambda y, m, la, lo: y in (1995, 1996, 1997, 1998)))
    with pytest.raises(InsufficientReferenceError, match="Only 26 of 30"):
        era5_land_temperature_anomaly(client, **params())


def test_missing_reference_years_are_reported_when_the_minimum_allows(make_client):
    client, _ = make_client(make_builder(nan_if=lambda y, m, la, lo: y in (1995, 1996)))

    result = era5_land_temperature_anomaly(client, **params(), min_reference_years=20)

    assert result.reference_years_used == 28
    assert [e.year for e in result.reference_years_excluded] == [1995, 1996]
    assert any("excluded" in text for text in result.limitations)


def test_short_reference_and_target_inside_reference_are_flagged(make_client):
    client, _ = make_client(make_builder())

    result = era5_land_temperature_anomaly(
        client,
        **params(target_end_month=YearMonth(2020, 3), reference_start_year=2001),
        min_reference_years=20,
    )

    assert result.reference_years_used == 20
    assert result.target_in_reference_period is True
    assert any("only 20 usable years" in text for text in result.limitations)
    assert any("contributed to its own reference mean" in text for text in result.limitations)


@pytest.mark.parametrize(
    ("overrides", "extra", "error"),
    [
        ({"target_end_month": YearMonth(2026, 10)}, {}, DataNotAvailableError),
        ({"reference_end_year": 2027}, {}, DataNotAvailableError),
        ({"target_end_month": YearMonth(1949, 12)}, {}, OutsideCoverageError),
        ({"latitude": -90.0, "longitude": 0.0}, {}, OutsideCoverageError),
        ({"timescale_months": 0}, {}, ValueError),
        ({"reference_start_year": 2020, "reference_end_year": 1991}, {}, ValueError),
        ({}, {"land_fallback_max_km": 99.0}, ValueError),
    ],
)
def test_invalid_requests_make_no_cds_requests(make_client, overrides, extra, error):
    client, downloader = make_client(make_builder())
    with pytest.raises(error):
        era5_land_temperature_anomaly(client, **params(**overrides), **extra)
    assert downloader.calls == []