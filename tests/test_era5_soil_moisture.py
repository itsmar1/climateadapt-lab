"""Offline tests for the ERA5-Land soil-water variables. No CDS access or network."""

from __future__ import annotations

import pytest

from climateadapt.data.era5_land import (
    VARIABLES,
    Era5LandClient,
    Era5LandMonthlyStore,
    Era5MonthValue,
    Era5PointSeries,
    day_weighted_mean,
)
from climateadapt.data.errors import DataIntegrityError, MissingDataError
from climateadapt.data.periods import YearMonth
from era5_helpers import LAT, LON, Builder, FakeDownloader

JAN, FEB, MAR = YearMonth(2024, 1), YearMonth(2024, 2), YearMonth(2024, 3)
NAN = float("nan")
UNIT_SPELLINGS = ["m**3 m**-3", "m3 m-3", "m^3 m^-3", "m3/m3"]


def soil_builder(value_fn, units="m**3 m**-3"):
    return Builder(value_fn, var="swvl1", units=units)


def wet(year, month, lat, lon):
    return 0.25 + 0.01 * month


@pytest.fixture
def make_client(tmp_path, today):
    def build(builder):
        downloader = FakeDownloader(builder)
        store = Era5LandMonthlyStore(
            cache_dir=tmp_path / "era5", downloader=downloader, today=lambda: today
        )
        return Era5LandClient(store), downloader

    return build


@pytest.mark.parametrize(
    ("name", "short", "depth"),
    [
        ("volumetric_soil_water_layer_1", "swvl1", "0-7 cm"),
        ("volumetric_soil_water_layer_2", "swvl2", "7-28 cm"),
        ("volumetric_soil_water_layer_3", "swvl3", "28-100 cm"),
    ],
)
def test_layers_are_registered_with_documented_depths(name, short, depth):
    spec = VARIABLES[name]
    assert spec.cds_name == name
    assert spec.file_short_names == (short,)
    assert spec.output_units == "m3/m3"
    assert depth in spec.description


def test_layer_4_is_not_registered_because_its_depth_is_contested():
    assert "volumetric_soil_water_layer_4" not in VARIABLES


def test_values_pass_through_without_conversion(make_client):
    client, downloader = make_client(soil_builder(wet))

    series = client.monthly_point_series("volumetric_soil_water_layer_1", LAT, LON, JAN, MAR)

    assert series.units == "m3/m3"
    assert [v.value for v in series.values] == pytest.approx([0.26, 0.27, 0.28], abs=1e-6)
    request = downloader.calls[0][1]
    assert request["variable"] == ["volumetric_soil_water_layer_1"]
    assert request["month"] == ["01", "02", "03"]


@pytest.mark.parametrize("units", UNIT_SPELLINGS)
def test_accepted_unit_spellings(make_client, units):
    client, _ = make_client(soil_builder(wet, units=units))
    series = client.monthly_point_series("volumetric_soil_water_layer_1", LAT, LON, JAN, JAN)
    assert series.values[0].value == pytest.approx(0.26, abs=1e-6)


@pytest.mark.parametrize("units", ["kg m-2", "%", "K"])
def test_other_units_are_rejected(make_client, units):
    client, _ = make_client(soil_builder(wet, units=units))
    with pytest.raises(DataIntegrityError, match="units"):
        client.monthly_point_series("volumetric_soil_water_layer_1", LAT, LON, JAN, JAN)


@pytest.mark.parametrize("bad", [1.5, -0.1])
def test_implausible_values_are_rejected(make_client, bad):
    client, _ = make_client(soil_builder(lambda y, m, la, lo: bad))
    with pytest.raises(DataIntegrityError, match="Implausible volumetric soil water"):
        client.monthly_point_series("volumetric_soil_water_layer_1", LAT, LON, JAN, JAN)


def test_masked_months_are_missing_and_block_the_window_mean(make_client):
    client, _ = make_client(
        soil_builder(lambda y, m, la, lo: NAN if m == 2 else 0.3)
    )
    series = client.monthly_point_series("volumetric_soil_water_layer_1", LAT, LON, JAN, MAR)

    assert series.values[1].value is None
    with pytest.raises(MissingDataError, match="2024-02"):
        day_weighted_mean(series)


def test_land_fallback_works_for_soil_water(make_client):
    def value(year, month, lat, lon):
        if lon == -9.7 or (lat == 30.4 and lon == -9.6):
            return NAN
        return 0.1 + 0.01 * round((lat - 30.0) * 10) + 0.001 * round((lon + 10.0) * 10)

    client, _ = make_client(soil_builder(value))
    series = client.monthly_point_series(
        "volumetric_soil_water_layer_1", LAT, LON, JAN, MAR, land_fallback_max_km=15.0
    )

    assert series.land_fallback.used is True
    assert (series.grid_point_latitude, series.grid_point_longitude) == (30.5, -9.6)
    assert [v.value for v in series.values] == pytest.approx([0.154] * 3, abs=1e-6)


def _manual_series(units, entries):
    return Era5PointSeries(
        dataset_id="reanalysis-era5-land-monthly-means",
        dataset_name="test",
        variable="volumetric_soil_water_layer_1",
        description="test",
        units=units,
        requested_latitude=0.0,
        requested_longitude=0.0,
        grid_point_latitude=0.0,
        grid_point_longitude=0.0,
        values=[
            Era5MonthValue(
                year=y, 
                month=m, 
                value=v, 
                status="ok" if v is not None else "missing_value", notes=[]
            )
            for y, m, v in entries
        ],
        provenance=[],
        limitations=[],
    )


def test_day_weighted_mean_respects_month_lengths():
    series = _manual_series("m3/m3", [(2023, 1, 0.2), (2023, 2, 0.3)])
    assert day_weighted_mean(series) == pytest.approx((31 * 0.2 + 28 * 0.3) / 59)


def test_day_weighted_mean_refuses_precipitation_totals():
    series = _manual_series("mm/month", [(2023, 1, 10.0)])
    with pytest.raises(ValueError, match="total_precipitation_mm"):
        day_weighted_mean(series)