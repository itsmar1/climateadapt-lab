"""Offline tests for the ERA5-Land endpoints, bundle, and jobs. No network."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from climateadapt.api.dependencies import get_chirps_client, get_era5_client, get_job_store
from climateadapt.api.jobs import JobStore
from climateadapt.api.main import create_app
from climateadapt.data.chirps import ChirpsV3Client
from climateadapt.data.era5_land import Era5LandClient, Era5LandMonthlyStore
from climateadapt.data.errors import DataNotAvailableError
from climateadapt.indicators.units import days_in_month
from era5_helpers import LAT, LON, Builder, FakeDownloader

TERMINAL = ("succeeded", "failed", "timed_out")

ERA5_SPI_URL = "/v1/analysis/era5-spi"
ERA5_TEMP_URL = "/v1/analysis/era5-temperature-anomaly"
ERA5_SOIL_URL = "/v1/analysis/era5-soil-moisture-anomaly"
BUNDLE_URL = "/v1/analysis/environmental-bundle"


def poll(client, job_id, timeout=60.0):
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200
        snapshot = response.json()
        if snapshot["status"] in TERMINAL:
            return snapshot
        assert time.monotonic() < deadline, "job never reached a terminal state"
        time.sleep(0.05)


def t2m_value(year, month, lat, lon):
    return 280.0 + ((year * 12 + month) % 9)


def tp_value(year, month, lat, lon):
    return (0.5 + ((year * 12 + month) % 7)) / 1000.0 / days_in_month(year, month)


def sw_value(year, month, lat, lon):
    return 0.15 + 0.01 * ((year * 12 + month) % 6)


BUILDERS = {
    "2m_temperature": Builder(t2m_value, var="t2m", units="K"),
    "total_precipitation": Builder(tp_value, var="tp", units="m"),
    "volumetric_soil_water_layer_1": Builder(sw_value, var="swvl1", units="m**3 m**-3"),
    "volumetric_soil_water_layer_2": Builder(sw_value, var="swvl2", units="m**3 m**-3"),
    "volumetric_soil_water_layer_3": Builder(sw_value, var="swvl3", units="m**3 m**-3"),
}


@pytest.fixture
def era5_client(tmp_path, today):
    def build(fail_variables=(), sleep_seconds=0.0):
        def dispatch(request, target):
            variable = request["variable"][0]
            if variable in fail_variables:
                raise DataNotAvailableError(f"synthetic {variable} outage")
            if sleep_seconds:
                time.sleep(sleep_seconds)
            return BUILDERS[variable](request, target)

        store = Era5LandMonthlyStore(
            cache_dir=tmp_path / "era5",
            downloader=FakeDownloader(dispatch),
            today=lambda: today,
        )
        return Era5LandClient(store)

    return build


@pytest.fixture
def chirps_client(make_store, http_mock, season_routes):
    def build():
        pairs = {(y, m) for y in [*range(2011, 2021), 2024] for m in (1, 2, 3)}
        routes = season_routes(pairs, lambda y, m: 20.0 + ((y + m) % 9))
        http, _ = http_mock(routes)
        return ChirpsV3Client(make_store(http))

    return build


@pytest.fixture
def api(era5_client, chirps_client):
    stores = []

    def build(fail_variables=(), sleep_seconds=0.0, timeout_seconds=900.0, max_jobs=1000):
        store = JobStore(timeout_seconds=timeout_seconds, max_jobs=max_jobs)
        stores.append(store)
        app = create_app()
        app.dependency_overrides[get_chirps_client] = chirps_client
        app.dependency_overrides[get_era5_client] = lambda: era5_client(
            fail_variables=fail_variables, sleep_seconds=sleep_seconds
        )
        app.dependency_overrides[get_job_store] = lambda: store
        return TestClient(app)

    build.stores = stores  # let tests pre-fill or inspect the injected store
    yield build
    for store in stores:
        store.shutdown()


def era5_payload(**overrides):
    body = {
        "latitude": LAT,
        "longitude": LON,
        "target_end_month": "2024-03",
        "timescale_months": 3,
        "reference_start_year": 2011,
        "reference_end_year": 2020,
        "min_reference_years": 10,
    }
    body.update(overrides)
    return body


def test_era5_spi_submit_and_poll_success(api):
    client = api()

    submitted = client.post(ERA5_SPI_URL, json=era5_payload())
    assert submitted.status_code == 202
    job = submitted.json()
    assert job["status_url"].endswith(f"/v1/jobs/{job['job_id']}")

    snapshot = poll(client, job["job_id"])
    assert snapshot["status"] == "succeeded"
    assert snapshot["progress"] == {"completed_steps": 1, "total_steps": 1}
    result = snapshot["result"]
    assert result["indicator"] == "standardized_precipitation_index"
    assert result["reference_years_used"] == 10


def test_era5_temperature_submit_and_poll_success(api):
    client = api()

    submitted = client.post(ERA5_TEMP_URL, json=era5_payload())
    assert submitted.status_code == 202

    snapshot = poll(client, submitted.json()["job_id"])
    assert snapshot["status"] == "succeeded"
    assert snapshot["result"]["indicator"] == "temperature_window_anomaly"
    assert isinstance(snapshot["result"]["anomaly_c"], float)


def test_era5_soil_moisture_layer_2_success(api):
    client = api()

    submitted = client.post(
        ERA5_SOIL_URL, json=era5_payload(variable="volumetric_soil_water_layer_2")
    )
    assert submitted.status_code == 202

    snapshot = poll(client, submitted.json()["job_id"])
    assert snapshot["status"] == "succeeded"
    result = snapshot["result"]
    assert result["indicator"] == "soil_moisture_window_anomaly"
    assert result["variable"] == "volumetric_soil_water_layer_2"
    assert result["layer_depth"] == "7-28 cm"


def test_bundle_all_ok_reports_every_indicator(api):
    client = api()

    submitted = client.post(BUNDLE_URL, json=era5_payload())
    assert submitted.status_code == 202

    snapshot = poll(client, submitted.json()["job_id"])
    assert snapshot["status"] == "succeeded"
    bundle = snapshot["result"]
    assert bundle["indicator"] == "environmental_bundle"
    assert [entry["indicator"] for entry in bundle["entries"]] == [
        "chirps_spi",
        "era5_spi",
        "era5_temperature_anomaly",
        "era5_soil_moisture_anomaly",
    ]
    for entry in bundle["entries"]:
        assert entry["status"] == "ok", entry
        assert entry["error_type"] is None
        assert entry["result"] is not None
        assert entry["result"]["limitations"]
        assert entry["grid_point_latitude"] is not None
        assert "severity" not in entry["result"] and "category" not in entry["result"]
    assert "severity" not in snapshot and "composite" not in str(snapshot).lower()


def test_bundle_reports_partial_failure_without_hiding_it(api):
    client = api(fail_variables=("volumetric_soil_water_layer_1",))

    submitted = client.post(BUNDLE_URL, json=era5_payload())
    snapshot = poll(client, submitted.json()["job_id"])

    assert snapshot["status"] == "succeeded"
    by_name = {entry["indicator"]: entry for entry in snapshot["result"]["entries"]}
    soil = by_name["era5_soil_moisture_anomaly"]
    assert soil["status"] == "failed"
    assert soil["error_type"] == "data_not_available"
    assert "synthetic" in soil["error_message"]
    assert soil["result"] is None
    for name in ("chirps_spi", "era5_spi", "era5_temperature_anomaly"):
        assert by_name[name]["status"] == "ok", name


def test_bundle_subset_marks_the_rest_skipped(api):
    client = api()

    submitted = client.post(BUNDLE_URL, json=era5_payload(indicators=["era5_spi"]))
    snapshot = poll(client, submitted.json()["job_id"])

    by_name = {entry["indicator"]: entry for entry in snapshot["result"]["entries"]}
    assert by_name["era5_spi"]["status"] == "ok"
    for name in ("chirps_spi", "era5_temperature_anomaly", "era5_soil_moisture_anomaly"):
        skipped = by_name[name]
        assert skipped["status"] == "skipped"
        assert skipped["result"] is None
        assert skipped["grid_point_latitude"] is None
        assert skipped["requested_latitude"] == LAT


def test_unknown_job_returns_job_not_found(api):
    client = api()

    response = client.get("/v1/jobs/no-such-job")

    assert response.status_code == 404
    assert response.json() == {
        "detail": [{"loc": [], "msg": "Unknown or expired job id.", "type": "job_not_found"}]
    }


def test_slow_job_times_out(api):
    client = api(sleep_seconds=0.3, timeout_seconds=0.05)

    submitted = client.post(ERA5_SPI_URL, json=era5_payload())
    snapshot = poll(client, submitted.json()["job_id"])

    assert snapshot["status"] == "timed_out"
    assert snapshot["error"]["type"] == "timeout"


def test_full_store_returns_503_server_busy(api):
    client = api(max_jobs=1)
    store = api.stores[-1]
    release = threading.Event()

    def gated(progress):
        assert release.wait(timeout=30.0)
        return {"ok": True}

    store.submit("blocker", 1, gated)
    try:
        response = client.post(ERA5_SPI_URL, json=era5_payload())

        assert response.status_code == 503
        assert response.json() == {
            "detail": [
                {
                    "loc": [],
                    "msg": "Job store is at capacity (1 jobs); retry shortly.",
                    "type": "server_busy",
                }
            ]
        }
    finally:
        release.set()


def test_cors_preflight_allows_the_vite_origin(api):
    client = api()

    response = client.options(
        BUNDLE_URL,
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_does_not_allow_unknown_origins(api):
    client = api()

    response = client.options(
        BUNDLE_URL,
        headers={
            "Origin": "http://evil.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("url", [ERA5_SPI_URL, ERA5_TEMP_URL, ERA5_SOIL_URL, BUNDLE_URL])
def test_validation_errors_never_echo_input(api, url):
    client = api()

    response = client.post(
        url, json=era5_payload(target_end_month="2024-13", timescale_months=99)
    )

    assert response.status_code == 422
    assert "2024-13" not in response.text
    assert "99" not in response.text


def test_soil_variable_rejects_unknown_layers(api):
    client = api()

    response = client.post(
        ERA5_SOIL_URL, json=era5_payload(variable="volumetric_soil_water_layer_4")
    )

    assert response.status_code == 422


def test_openapi_contains_the_new_routes(api):
    client = api()

    spec = client.get("/openapi.json").json()

    for path in (ERA5_SPI_URL, ERA5_TEMP_URL, ERA5_SOIL_URL, BUNDLE_URL, "/v1/jobs/{job_id}"):
        assert path in spec["paths"], path
