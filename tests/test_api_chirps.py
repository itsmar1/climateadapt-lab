import httpx
import pytest
from fastapi.testclient import TestClient

from climateadapt.api.dependencies import get_chirps_client
from climateadapt.api.main import create_app
from climateadapt.data.chirps import ChirpsV3Client

URL = "/v1/analysis/chirps-rainfall-anomaly"
MAM = (3, 4, 5)


def mam_pairs(years):
    return [(y, m) for y in years for m in MAM]


@pytest.fixture
def api(make_store, http_mock):
    def build(routes):
        http, calls = http_mock(routes)
        chirps = ChirpsV3Client(make_store(http))
        app = create_app()
        app.dependency_overrides[get_chirps_client] = lambda: chirps
        return TestClient(app), calls

    return build


@pytest.fixture
def payload(cell_center):
    def build(**overrides):
        lat, lon = cell_center(5, 7)
        body = {
            "latitude": lat,
            "longitude": lon,
            "observed_start_month": "2024-03",
            "window_months": 3,
            "baseline_start_year": 2011,
            "baseline_end_year": 2020,
        }
        body.update(overrides)
        return body

    return build


@pytest.fixture
def standard_routes(season_routes):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    return season_routes(pairs, lambda y, m: 24.0 if y == 2024 else 30.0)


def test_success(api, payload, standard_routes):
    client, calls = api(standard_routes)

    response = client.post(URL, json=payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["percentage_anomaly"] == pytest.approx(-20.0)
    assert body["observed_total_mm"] == pytest.approx(72.0)
    assert body["baseline_mean_mm"] == pytest.approx(90.0)
    assert body["direction"] == "below_baseline"
    assert body["baseline_years_used"] == 10
    assert len(body["source_files"]) == 33
    assert body["data_source"].startswith("CHIRPS v3.0 Final")
    assert body["citation"] and body["doi"]
    assert body["limitations"]
    assert "severity" not in body
    assert len(calls) == 33


def test_zero_baseline_returns_undefined(api, payload, season_routes):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(pairs, lambda y, m: 10.0 if y == 2024 else 0.0)
    client, _ = api(routes)

    body = client.post(URL, json=payload()).json()

    assert body["status"] == "undefined"
    assert body["percentage_anomaly"] is None
    assert body["message"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"baseline_start_year": 2020, "baseline_end_year": 2011},
        {"observed_start_month": "2024-13"},
        {"observed_start_month": "2024-3"},
        {"window_months": 13},
        {"window_months": 0},
        {"window_months": "3"},
        {"latitude": 91.0},
        {"unexpected": 1},
    ],
)
def test_invalid_requests_rejected_without_network(api, payload, standard_routes, overrides):
    client, calls = api(standard_routes)
    response = client.post(URL, json=payload(**overrides))
    assert response.status_code == 422
    assert calls == []


def test_outside_coverage_is_422_with_code(api, payload, standard_routes):
    client, calls = api(standard_routes)
    response = client.post(URL, json=payload(latitude=70.0, longitude=10.0))
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "outside_coverage"
    assert calls == []


def test_unavailable_period_is_404(api, payload, standard_routes):
    client, calls = api(standard_routes)
    response = client.post(URL, json=payload(observed_start_month="2026-09"))
    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "data_not_available"
    assert calls == []


def test_insufficient_baseline_is_422(api, payload, season_routes):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(
        pairs, lambda y, m: 24.0 if y == 2024 else 30.0, missing={(2012, 3), (2013, 5)}
    )
    client, _ = api(routes)

    response = client.post(URL, json=payload())

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["type"] == "insufficient_baseline"
    assert "Only 8 of 10" in detail["msg"]


def test_missing_observed_value_is_422(api, payload, season_routes):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(
        pairs, lambda y, m: 24.0 if y == 2024 else 30.0, missing={(2024, 4)}
    )
    client, _ = api(routes)

    response = client.post(URL, json=payload())

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "missing_data"


def test_upstream_failure_is_502(api, payload, season_routes):
    pairs = mam_pairs(range(2011, 2021)) + mam_pairs([2024])
    routes = season_routes(pairs, lambda y, m: 24.0 if y == 2024 else 30.0)
    routes["chirps-v3.0.2024.03.tif"] = lambda: httpx.Response(500)
    client, _ = api(routes)

    response = client.post(URL, json=payload())

    assert response.status_code == 502
    assert response.json()["detail"][0]["type"] == "download_error"


def test_endpoint_is_documented_in_openapi(api, standard_routes):
    client, _ = api(standard_routes)
    assert URL in client.get("/openapi.json").json()["paths"]