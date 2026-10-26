"""Offline tests for the ERA5-Land connector: no CDS access, credentials, or network."""

from __future__ import annotations

import hashlib
import math
import zipfile
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from climateadapt.config import Settings
from climateadapt.data.era5_land import (
    VARIABLES,
    CdsApiDownloader,
    Era5LandClient,
    Era5LandMonthlyStore,
    Era5MonthValue,
    Era5PointSeries,
    build_era5_land_client,
    day_weighted_mean_temperature_c,
    group_months_for_requests,
    total_precipitation_mm,
)
from climateadapt.data.errors import (
    DataIntegrityError,
    DataNotAvailableError,
    DownloadError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.data.periods import YearMonth

LAT, LON = 30.43, -9.61  # nearest 0.1 degree grid point is (30.4, -9.6)


def _axis(low: float, high: float) -> list[float]:
    ints = range(math.ceil(low * 10 - 1e-9), math.floor(high * 10 + 1e-9) + 1)
    return [i / 10 for i in ints]


def temp_k(year, month, lat, lon):
    return 280.0 + month  # Jan 281 K = 7.85 degC


def precip_m(year, month, lat, lon):
    return 0.001 * month  # Jan 0.001 m/day


class Builder:
    """Write a synthetic CDS-like NetCDF that honours the request's years/months/area."""

    def __init__(
        self,
        value_fn,
        *,
        var="t2m",
        units="K",
        time_name="valid_time",
        lat_name="latitude",
        lon_name="longitude",
        lon_offset=0.0,
        zipped=False,
        extra_dim=None,
        drop_months=(),
    ):
        self.value_fn = value_fn
        self.var = var
        self.units = units
        self.time_name = time_name
        self.lat_name = lat_name
        self.lon_name = lon_name
        self.lon_offset = lon_offset
        self.zipped = zipped
        self.extra_dim = extra_dim
        self.drop = set(drop_months)

    def __call__(self, request, target: Path) -> None:
        north, west, south, east = request["area"]
        lats = list(reversed(_axis(south, north)))
        lons = _axis(west, east)
        years = sorted(int(y) for y in request["year"])
        months = sorted(int(m) for m in request["month"])
        stamps = [(y, m) for y in years for m in months if (y, m) not in self.drop]
        times = np.array(
            [np.datetime64(f"{y:04d}-{m:02d}-01T00:00:00", "ns") for y, m in stamps]
        )
        data = np.array(
            [[[self.value_fn(y, m, la, lo) for lo in lons] for la in lats] for y, m in stamps],
            dtype="float32",
        )
        dims = [self.time_name, self.lat_name, self.lon_name]
        coords = {
            self.time_name: times,
            self.lat_name: lats,
            self.lon_name: [lo + self.lon_offset for lo in lons],
        }
        if self.extra_dim is not None:
            data = np.repeat(data[:, None], self.extra_dim, axis=1)
            dims.insert(1, "number")
            coords["number"] = np.arange(self.extra_dim)
        dataset = xr.Dataset({self.var: (dims, data, {"units": self.units})}, coords=coords)

        if self.zipped:
            tmp = target.with_suffix(".tmpnc")
            dataset.to_netcdf(tmp)
            with zipfile.ZipFile(target, "w") as archive:
                archive.write(tmp, "data_0.nc")
            tmp.unlink()
        else:
            dataset.to_netcdf(target)


class FakeDownloader:
    def __init__(self, builder):
        self.builder = builder
        self.calls: list[tuple[str, dict]] = []

    def download(self, dataset, request, target):
        self.calls.append((dataset, dict(request)))
        self.builder(request, Path(target))


@pytest.fixture
def make_client(tmp_path, today):
    def build(builder, *, allow_downloads=True):
        downloader = FakeDownloader(builder)
        store = Era5LandMonthlyStore(
            cache_dir=tmp_path / "era5",
            downloader=downloader,
            allow_downloads=allow_downloads,
            today=lambda: today,
        )
        return Era5LandClient(store), downloader

    return build


JAN = YearMonth(2024, 1)
MAR = YearMonth(2024, 3)


# ---------------------------------------------------------------- request building


def test_request_shape(make_client):
    client, downloader = make_client(Builder(temp_k))
    client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    dataset, request = downloader.calls[0]
    assert dataset == "reanalysis-era5-land-monthly-means"
    assert request == {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": ["2m_temperature"],
        "year": ["2024"],
        "month": ["01", "02", "03"],
        "time": ["00:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": [30.58, -9.76, 30.28, -9.46],
    }


def test_months_with_same_month_set_share_one_request():
    months = [YearMonth(y, m) for y in (2011, 2012, 2024) for m in (1, 2, 3)]
    assert group_months_for_requests(months) == [([2011, 2012, 2024], [1, 2, 3])]


def test_year_boundary_window_needs_two_exact_requests(make_client):
    client, downloader = make_client(Builder(temp_k))
    series = client.monthly_point_series(
        "2m_temperature", LAT, LON, YearMonth(2011, 11), YearMonth(2012, 1)
    )

    assert len(series.values) == 3
    assert len(downloader.calls) == 2
    first, second = (call[1] for call in downloader.calls)
    assert (first["year"], first["month"]) == (["2011"], ["11", "12"])
    assert (second["year"], second["month"]) == (["2012"], ["01"])


# ---------------------------------------------------------------- conversions


def test_temperature_converted_to_celsius(make_client):
    client, _ = make_client(Builder(temp_k))
    series = client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    assert series.units == "degC"
    assert [v.value for v in series.values] == pytest.approx([7.85, 8.85, 9.85], abs=1e-3)
    assert (series.grid_point_latitude, series.grid_point_longitude) == (30.4, -9.6)


def test_precipitation_uses_days_in_month(make_client):
    client, _ = make_client(Builder(precip_m, var="tp", units="m"))
    series = client.monthly_point_series("total_precipitation", LAT, LON, JAN, MAR)

    assert series.units == "mm/month"
    # Jan 0.001 * 1000 * 31, Feb 2024 (29 days) 0.002 * 1000 * 29, Mar 0.003 * 1000 * 31
    assert [v.value for v in series.values] == pytest.approx([31.0, 58.0, 93.0], abs=1e-3)
    assert total_precipitation_mm(series) == pytest.approx(182.0, abs=1e-3)


def test_negative_packing_noise_is_zeroed_with_a_note(make_client):
    client, _ = make_client(
        Builder(lambda y, m, la, lo: -1e-9 if m == 1 else 0.001, var="tp", units="m")
    )
    series = client.monthly_point_series("total_precipitation", LAT, LON, JAN, YearMonth(2024, 2))

    assert series.values[0].value == 0.0
    assert series.values[0].notes
    assert series.values[1].notes == []


def test_large_negative_precipitation_is_rejected(make_client):
    client, _ = make_client(Builder(lambda y, m, la, lo: -0.01, var="tp", units="m"))
    with pytest.raises(DataIntegrityError, match="negative"):
        client.monthly_point_series("total_precipitation", LAT, LON, JAN, JAN)


def test_implausible_temperature_is_rejected(make_client):
    client, _ = make_client(Builder(lambda y, m, la, lo: 9.969e36))
    with pytest.raises(DataIntegrityError, match="Implausible"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, JAN)


def test_wrong_file_units_are_rejected_and_nothing_is_kept(tmp_path, make_client):
    client, _ = make_client(Builder(temp_k, units="degC"))
    with pytest.raises(DataIntegrityError, match="units"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, JAN)
    assert list((tmp_path / "era5" / "raw").iterdir()) == []


# ---------------------------------------------------------------- missing values


def test_ocean_nan_is_missing_not_zero(make_client):
    client, _ = make_client(
        Builder(lambda y, m, la, lo: float("nan") if m == 2 else 0.001, var="tp", units="m")
    )
    series = client.monthly_point_series("total_precipitation", LAT, LON, JAN, MAR)

    assert series.values[1].value is None
    assert series.values[1].status == "missing_value"
    with pytest.raises(MissingDataError, match="2024-02"):
        total_precipitation_mm(series)


# ---------------------------------------------------------------- caching and provenance


def test_second_call_is_served_from_cache(make_client):
    client, downloader = make_client(Builder(temp_k))
    first = client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)
    second = client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    assert len(downloader.calls) == 1
    assert [v.value for v in first.values] == [v.value for v in second.values]


def test_cache_persists_across_store_instances_and_works_offline(make_client):
    client, _ = make_client(Builder(temp_k))
    client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    offline_client, offline_downloader = make_client(Builder(temp_k), allow_downloads=False)
    series = offline_client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    assert offline_downloader.calls == []
    assert len(series.values) == 3


def test_offline_mode_without_cache_fails_without_requests(make_client):
    client, downloader = make_client(Builder(temp_k), allow_downloads=False)
    with pytest.raises(DataNotAvailableError, match="downloads are disabled"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)
    assert downloader.calls == []


def test_provenance_is_complete_and_matches_the_kept_file(make_client):
    client, _ = make_client(Builder(temp_k))
    series = client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    assert len(series.provenance) == 1
    prov = series.provenance[0]
    raw = Path(prov.raw_file_path)
    assert raw.exists()
    assert prov.raw_file_sha256 == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert prov.raw_file_size_bytes == raw.stat().st_size
    assert prov.dataset_id == "reanalysis-era5-land-monthly-means"
    assert prov.request["variable"] == ["2m_temperature"]
    assert "cds.68d2bb30" in prov.doi
    assert prov.delivered_as_zip is False
    assert any("reanalysis" in text for text in series.limitations)


# ---------------------------------------------------------------- file-format robustness


@pytest.mark.parametrize(
    "kwargs",
    [
        {"time_name": "time"},
        {"lat_name": "lat", "lon_name": "lon"},
        {"lon_offset": 360.0},  # 0..360 longitude convention
        {"extra_dim": 1},  # size-1 'number'/'expver' style dimension
    ],
)
def test_alternative_netcdf_layouts_are_handled(make_client, kwargs):
    client, _ = make_client(Builder(temp_k, **kwargs))
    series = client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    assert [v.value for v in series.values] == pytest.approx([7.85, 8.85, 9.85], abs=1e-3)
    assert series.grid_point_longitude == pytest.approx(-9.6)


def test_unexpected_multi_valued_extra_dimension_is_rejected(make_client):
    client, _ = make_client(Builder(temp_k, extra_dim=2))
    with pytest.raises(DataIntegrityError, match="dimension"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, JAN)


def test_zip_delivery_is_unpacked(make_client):
    client, _ = make_client(Builder(temp_k, zipped=True))
    series = client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)

    assert series.provenance[0].delivered_as_zip is True
    assert len(series.values) == 3


def test_zip_with_two_netcdf_files_is_rejected(tmp_path, make_client):
    def two_files(request, target):
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("a.nc", b"x")
            archive.writestr("b.nc", b"y")

    client, _ = make_client(two_files)
    with pytest.raises(DataIntegrityError, match="exactly one"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, JAN)
    assert list((tmp_path / "era5" / "raw").iterdir()) == []


def test_html_instead_of_netcdf_is_rejected(tmp_path, make_client):
    client, _ = make_client(lambda request, target: target.write_bytes(b"<html>oops</html>"))
    with pytest.raises(DataIntegrityError, match="NetCDF"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, JAN)
    assert list((tmp_path / "era5" / "raw").iterdir()) == []


def test_grid_too_far_from_the_point_is_rejected(make_client):
    def far_away(request, target):
        dataset = xr.Dataset(
            {"t2m": (["valid_time", "latitude", "longitude"], np.full((1, 2, 2), 285.0), {"units": "K"})},
            coords={
                "valid_time": np.array([np.datetime64("2024-01-01T00:00:00", "ns")]),
                "latitude": [10.1, 10.0],
                "longitude": [50.0, 50.1],
            },
        )
        dataset.to_netcdf(target)

    client, _ = make_client(far_away)
    with pytest.raises(DataIntegrityError, match="grid point"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, JAN)


def test_requested_month_missing_from_file_is_rejected(make_client):
    client, _ = make_client(Builder(temp_k, drop_months={(2024, 2)}))
    with pytest.raises(DataIntegrityError, match="2024-02"):
        client.monthly_point_series("2m_temperature", LAT, LON, JAN, MAR)


# ---------------------------------------------------------------- fail-fast validation


def test_unsupported_variable_makes_no_request(make_client):
    client, downloader = make_client(Builder(temp_k))
    with pytest.raises(ValueError, match="Unsupported"):
        client.monthly_point_series("skin_temperature", LAT, LON, JAN, JAN)
    assert downloader.calls == []


@pytest.mark.parametrize(
    ("lat", "lon", "start", "end", "error"),
    [
        (-90.0, 0.0, JAN, JAN, OutsideCoverageError),  # south edge exclusive
        (91.0, 0.0, JAN, JAN, ValueError),
        (LAT, LON, YearMonth(1949, 12), YearMonth(1950, 1), OutsideCoverageError),
        (LAT, LON, YearMonth(2026, 9), YearMonth(2026, 10), DataNotAvailableError),
        (LAT, LON, MAR, JAN, ValueError),
    ],
)
def test_invalid_requests_make_no_request(make_client, lat, lon, start, end, error):
    client, downloader = make_client(Builder(temp_k))
    with pytest.raises(error):
        client.monthly_point_series("2m_temperature", lat, lon, start, end)
    assert downloader.calls == []


# ---------------------------------------------------------------- aggregation helpers


def _manual_series(variable, units, entries):
    return Era5PointSeries(
        dataset_id="reanalysis-era5-land-monthly-means",
        dataset_name="test",
        variable=variable,
        description="test",
        units=units,
        requested_latitude=0.0,
        requested_longitude=0.0,
        grid_point_latitude=0.0,
        grid_point_longitude=0.0,
        values=[
            Era5MonthValue(
                year=y, month=m, value=v, status="ok" if v is not None else "missing_value", notes=[]
            )
            for y, m, v in entries
        ],
        provenance=[],
        limitations=[],
    )


def test_day_weighted_mean_respects_month_lengths():
    non_leap = _manual_series("2m_temperature", "degC", [(2023, 1, 10.0), (2023, 2, 20.0)])
    leap = _manual_series("2m_temperature", "degC", [(2024, 1, 10.0), (2024, 2, 20.0)])

    assert day_weighted_mean_temperature_c(non_leap) == pytest.approx((310 + 560) / 59)
    assert day_weighted_mean_temperature_c(leap) == pytest.approx((310 + 580) / 60)


def test_aggregates_refuse_missing_values_and_wrong_units():
    with_gap = _manual_series("2m_temperature", "degC", [(2024, 1, 10.0), (2024, 2, None)])
    with pytest.raises(MissingDataError):
        day_weighted_mean_temperature_c(with_gap)
    with pytest.raises(ValueError, match="precipitation"):
        total_precipitation_mm(with_gap)
    precip = _manual_series("total_precipitation", "mm/month", [(2024, 1, 5.0)])
    with pytest.raises(ValueError, match="temperature"):
        day_weighted_mean_temperature_c(precip)


# ---------------------------------------------------------------- CDS adapter


class _FakeResult:
    def __init__(self, payload):
        self.payload = payload

    def download(self, target):
        Path(target).write_bytes(self.payload)


class _FakeCdsClient:
    def __init__(self, *, error=None, payload=b"nc"):
        self.error = error
        self.payload = payload
        self.calls = []

    def retrieve(self, dataset, request):
        self.calls.append((dataset, dict(request)))
        if self.error is not None:
            raise self.error
        return _FakeResult(self.payload)


def test_cds_adapter_calls_retrieve_then_download(tmp_path):
    fake = _FakeCdsClient(payload=b"hello")
    downloader = CdsApiDownloader(client_factory=lambda: fake)
    target = tmp_path / "out.bin"

    downloader.download("some-dataset", {"a": 1}, target)

    assert fake.calls == [("some-dataset", {"a": 1})]
    assert target.read_bytes() == b"hello"


def test_cds_not_available_yet_maps_to_data_not_available(tmp_path):
    fake = _FakeCdsClient(error=Exception("None of the data you have requested is available yet"))
    with pytest.raises(DataNotAvailableError):
        CdsApiDownloader(client_factory=lambda: fake).download("d", {}, tmp_path / "x")


def test_cds_other_errors_map_to_download_error_with_setup_hint(tmp_path):
    fake = _FakeCdsClient(error=Exception("401 Client Error: Unauthorized"))
    with pytest.raises(DownloadError, match="personal access token"):
        CdsApiDownloader(client_factory=lambda: fake).download("d", {}, tmp_path / "x")


def test_build_client_uses_configured_data_dir(tmp_path):
    client = build_era5_land_client(
        Settings(data_dir=tmp_path), downloader=FakeDownloader(Builder(temp_k))
    )
    assert tmp_path in client.store.cache_dir.parents


def test_variable_table_is_consistent():
    assert set(VARIABLES) == {"2m_temperature", "total_precipitation"}
    assert VARIABLES["total_precipitation"].output_units == "mm/month"