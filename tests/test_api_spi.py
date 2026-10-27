import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from climateadapt.api.dependencies import get_chirps_client
from climateadapt.api.main import create_app
from climateadapt.data.chirps import ChirpsV3Client

URL = "/v1/analysis/chirps-spi"


def synthetic(year, month):
    return float(np.random.default_rng(year * 100 + month).gamma(2.5, 12.0))


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
            "target_end_month": "2024-03",
            "timescale_months": 1,
        }
        body.update(overrides)
        return body

    return build


@pytest.fixture
def routes(season_routes):
    pairs = {(y, 3) for y in [*range(1991, 2021), 2024]}
    return season_routes(pairs, synthetic)


def test_success(api, payload, routes):
    client, calls = api(routes)

    response = client.post(URL, json=payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["indicator"] == "standardized_precipitation_index"
    assert isinstance(body["spi"], float)
    assert 0.0 < body["cumulative_probability"] < 1.0
    assert body["reference_start_year"] == 1991 and body["reference_end_year"] == 2020
    assert body["reference_years_used"] == 30
    assert body["gamma_shape"] > 0 and body["gamma_scale_mm"] > 0
    assert body["citation"] and body["doi"] and body["limitations"]
    assert "severity" not in body and "category" not in body
    assert len(calls) == 31


@pytest.mark.parametrize(
    "overrides",
    [
        {"timescale_months": 0},
        {"timescale_months": 49},
        {"timescale_months": "3"},
        {"target_end_month": "2024-13"},
        {"target_end_month": "2024-3"},
        {"reference_start_year": 2020, "reference_end_year": 1991},
        {"reference_start_year": 2011, "reference_end_year": 2020},  # 10 years < default 30
        {"min_reference_years": 9},
        {"latitude": 91.0},
        {"unexpected": 1},
    ],
)
def test_invalid_requests_are_422_without_network(api, payload, routes, overrides):
    client, calls = api(routes)
    response = client.post(URL, json=payload(**overrides))
    assert response.status_code == 422
    assert calls == []


def test_a_shorter_reference_is_accepted_when_the_minimum_is_lowered(api, payload, season_routes):
    pairs = {(y, 3) for y in [*range(2001, 2021), 2024]}
    client, _ = api(season_routes(pairs, synthetic))

    response = client.post(
        URL, json=payload(reference_start_year=2001, min_reference_years=20)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reference_years_used"] == 20
    assert any("only 20 usable years" in text for text in body["limitations"])


def test_outside_coverage_is_422_with_code(api, payload, routes):
    client, calls = api(routes)
    response = client.post(URL, json=payload(latitude=70.0, longitude=10.0))
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "outside_coverage"
    assert calls == []


def test_unavailable_period_is_404(api, payload, routes):
    client, calls = api(routes)
    response = client.post(URL, json=payload(target_end_month="2026-10"))
    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "data_not_available"
    assert calls == []


def test_insufficient_reference_is_422(api, payload, season_routes):
    pairs = {(y, 3) for y in [*range(1991, 2021), 2024]}
    routes = season_routes(pairs, synthetic, missing={(y, 3) for y in (1995, 1996, 1997, 1998)})
    client, _ = api(routes)

    response = client.post(URL, json=payload())

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["type"] == "insufficient_reference"
    assert "Only 26 of 30" in detail["msg"]


def test_missing_target_value_is_422(api, payload, season_routes):
    pairs = {(y, 3) for y in [*range(1991, 2021), 2024]}
    client, _ = api(season_routes(pairs, synthetic, missing={(2024, 3)}))

    response = client.post(URL, json=payload())

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "missing_data"


def test_upstream_failure_is_502(api, payload, season_routes):
    pairs = {(y, 3) for y in [*range(1991, 2021), 2024]}
    routes = season_routes(pairs, synthetic)
    routes["chirps-v3.0.2024.03.tif"] = lambda: httpx.Response(500)
    client, _ = api(routes)

    response = client.post(URL, json=payload())

    assert response.status_code == 502
    assert response.json()["detail"][0]["type"] == "download_error"


def test_endpoint_is_documented_in_openapi(api, routes):
    client, _ = api(routes)
    assert URL in client.get("/openapi.json").json()["paths"]