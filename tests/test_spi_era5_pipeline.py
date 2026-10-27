"""Offline tests for the ERA5-Land SPI pipeline. No CDS access, credentials, or network."""

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
from climateadapt.indicators.spi import InsufficientReferenceError, compute_spi
from climateadapt.indicators.units import days_in_month
from climateadapt.pipelines.spi_era5 import era5_land_spi
from era5_helpers import LAT, LON, Builder, FakeDownloader


def mm(year, month):
    """Synthetic monthly total (mm)."""
    return float(np.random.default_rng(year * 100 + month).gamma(2.5, 12.0))


def make_builder(nan_if=None):
    def value_fn(year, month, lat, lon):
        if nan_if is not None and nan_if(year, month, lat, lon):
            return float("nan")
        return mm(year, month) / 1000.0 / days_in_month(year, month)  # m/day

    return Builder(value_fn, var="tp", units="m")


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


MASK_NEAREST_AND_WEST = lambda y, m, la, lo: lo == -9.7 or (la == 30.4 and lo == -9.6)  # noqa: E731


def test_single_month_spi_matches_the_pure_calculation(make_client):
    client, downloader = make_client(make_builder())

    result = era5_land_spi(client, **params())

    monthly = {YearMonth(y, 3): mm(y, 3) for y in [*range(1991, 2021), 2024]}
    expected = compute_spi(monthly, YearMonth(2024, 3), 1, 1991, 2020)
    assert result.status == "ok"
    assert result.spi == pytest.approx(expected.spi, abs=1e-3)
    assert result.cumulative_probability == pytest.approx(expected.cumulative_probability, abs=1e-3)
    assert result.window_total_mm == pytest.approx(mm(2024, 3), abs=1e-3)
    assert result.reference_years_used == 30
    assert result.reference_years_excluded == []
    assert result.target_in_reference_period is False
    assert result.land_fallback is None
    assert (result.grid_point_latitude, result.grid_point_longitude) == (30.4, -9.6)
    assert result.reference_spi_std > 0
    assert "cds.68d2bb30" in result.doi
    assert any("reanalysis" in text for text in result.limitations)
    assert any("not a measure of agricultural drought damage" in t for t in result.limitations)
    dumped = result.model_dump()
    assert "severity" not in dumped and "category" not in dumped

    # One small request for the target window, one grouped request for all 30 reference years.
    assert len(downloader.calls) == 2
    target_request, reference_request = (call[1] for call in downloader.calls)
    assert target_request["year"] == ["2024"]
    assert reference_request["year"] == [f"{y:04d}" for y in range(1991, 2021)]
    assert reference_request["month"] == ["03"]
    assert len(result.raw_files) == 2


def test_three_month_spi_uses_the_whole_window(make_client):
    client, downloader = make_client(make_builder())

    result = era5_land_spi(client, **params(timescale_months=3))

    monthly = {YearMonth(y, m): mm(y, m) for y in [*range(1991, 2021), 2024] for m in (1, 2, 3)}
    expected = compute_spi(monthly, YearMonth(2024, 3), 3, 1991, 2020)
    assert result.target_window_start == "2024-01"
    assert result.target_window_end == "2024-03"
    assert result.spi == pytest.approx(expected.spi, abs=1e-3)
    assert result.window_total_mm == pytest.approx(expected.window_total_mm, abs=1e-2)
    assert len(downloader.calls) == 2


def test_windows_crossing_a_year_boundary_are_assembled_correctly(make_client):
    client, _ = make_client(make_builder())

    result = era5_land_spi(
        client, **params(target_end_month=YearMonth(2024, 2), timescale_months=3)
    )

    monthly = {YearMonth(y, m): mm(y, m) for y in range(1990, 2025) for m in range(1, 13)}
    expected = compute_spi(monthly, YearMonth(2024, 2), 3, 1991, 2020)
    assert result.target_window_start == "2023-12"
    assert result.spi == pytest.approx(expected.spi, abs=1e-3)


def test_masked_nearest_point_needs_the_opt_in_fallback(make_client):
    client, _ = make_client(make_builder(nan_if=MASK_NEAREST_AND_WEST))

    with pytest.raises(MissingDataError, match="land_fallback_max_km"):
        era5_land_spi(client, **params())

    result = era5_land_spi(client, **params(), land_fallback_max_km=15.0)

    monthly = {YearMonth(y, 3): mm(y, 3) for y in [*range(1991, 2021), 2024]}
    expected = compute_spi(monthly, YearMonth(2024, 3), 1, 1991, 2020)
    assert result.status == "ok"
    assert result.land_fallback.used is True
    assert (result.grid_point_latitude, result.grid_point_longitude) == (30.5, -9.6)
    assert "neighbouring grid point" in result.limitations[0]
    assert result.spi == pytest.approx(expected.spi, abs=1e-3)


def test_a_different_neighbour_in_some_years_is_refused(make_client):
    def mask(year, month, lat, lon):
        return MASK_NEAREST_AND_WEST(year, month, lat, lon) or (
            year == 2005 and (lat, lon) == (30.5, -9.6)
        )

    client, _ = make_client(make_builder(nan_if=mask))
    with pytest.raises(DataIntegrityError, match="Grid point differs"):
        era5_land_spi(client, **params(), land_fallback_max_km=15.0)


def test_too_many_missing_reference_years_raise(make_client):
    client, _ = make_client(make_builder(nan_if=lambda y, m, la, lo: y in (1995, 1996, 1997, 1998)))
    with pytest.raises(InsufficientReferenceError, match="Only 26 of 30"):
        era5_land_spi(client, **params())


def test_missing_reference_years_are_reported_when_the_minimum_allows(make_client):
    client, _ = make_client(make_builder(nan_if=lambda y, m, la, lo: y in (1995, 1996)))

    result = era5_land_spi(client, **params(), min_reference_years=20)

    assert result.reference_years_used == 28
    assert [e.year for e in result.reference_years_excluded] == [1995, 1996]
    assert "missing data" in result.reference_years_excluded[0].reason


def test_windows_before_the_record_start_are_excluded(make_client):
    client, _ = make_client(make_builder())

    result = era5_land_spi(
        client,
        **params(
            target_end_month=YearMonth(2024, 1),
            timescale_months=2,
            reference_start_year=1950,
        ),
    )

    assert result.reference_years_used == 70
    assert [e.year for e in result.reference_years_excluded] == [1950]
    assert "before the ERA5-Land monthly record begins" in result.reference_years_excluded[0].reason


def test_short_reference_and_target_inside_reference_are_flagged(make_client):
    client, _ = make_client(make_builder())

    result = era5_land_spi(
        client,
        **params(target_end_month=YearMonth(2020, 3), reference_start_year=2001),
        min_reference_years=20,
    )

    assert result.reference_years_used == 20
    assert result.target_in_reference_period is True
    assert any("only 20 usable years" in text for text in result.limitations)
    assert any("contributed to its own calibration" in text for text in result.limitations)


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
        era5_land_spi(client, **params(**overrides), **extra)
    assert downloader.calls == []