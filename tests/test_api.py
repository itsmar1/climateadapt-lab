import pytest
from fastapi.testclient import TestClient

from climateadapt.api.main import create_app

URL = "/v1/analysis/rainfall-anomaly"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["environment"] in {"development", "test", "production"}


def test_rainfall_ok_below_baseline(client):
    response = client.post(
        URL,
        json={
            "observed_total_mm": 80.0,
            "baseline_mean_mm": 100.0,
            "data_origin": "synthetic_example",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["percentage_anomaly"] == pytest.approx(-20.0)
    assert body["absolute_difference_mm"] == pytest.approx(-20.0)
    assert body["direction"] == "below_baseline"
    assert body["indicator"] == "precipitation_percentage_anomaly"
    assert body["data_origin"] == "synthetic_example"
    assert body["limitations"]


def test_response_makes_no_severity_claim(client):
    body = client.post(URL, json={"observed_total_mm": 10.0, "baseline_mean_mm": 100.0}).json()
    assert "severity" not in body
    assert "drought_class" not in body


def test_rainfall_with_scenario_context(client):
    response = client.post(
        URL,
        json={
            "observed_total_mm": 120.0,
            "baseline_mean_mm": 100.0,
            "scenario": {
                "name": "Synthetic test field",
                "location": {"latitude": 30.4, "longitude": -9.6},
                "crop": "wheat",
                "observation_period": {"start_date": "2024-03-01", "end_date": "2024-05-31"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["percentage_anomaly"] == pytest.approx(20.0)
    assert body["direction"] == "above_baseline"
    assert body["scenario"]["crop"] == "wheat"
    assert body["data_origin"] == "user_supplied"


def test_zero_baseline_returns_explicit_undefined(client):
    response = client.post(URL, json={"observed_total_mm": 10.0, "baseline_mean_mm": 0.0})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "undefined"
    assert body["percentage_anomaly"] is None
    assert "undefined" in body["message"].lower()


@pytest.mark.parametrize(
    "payload",
    [
        {"observed_total_mm": -1.0, "baseline_mean_mm": 100.0},
        {"observed_total_mm": 1.0, "baseline_mean_mm": -100.0},
        {"baseline_mean_mm": 100.0},
        {"observed_total_mm": 10.0},
        {"observed_total_mm": 10.0, "baseline_mean_mm": 100.0, "unexpected": 1},
        {"observed_total_mm": 10.0, "baseline_mean_mm": 100.0, "data_origin": "satellite"},
        {"observed_total_mm": "ten", "baseline_mean_mm": 100.0},
        {"observed_total_mm": True, "baseline_mean_mm": 100.0},
        {
            "observed_total_mm": 10.0,
            "baseline_mean_mm": 100.0,
            "scenario": {"location": {"latitude": 123.0, "longitude": 0.0}},
        },
        {
            "observed_total_mm": 10.0,
            "baseline_mean_mm": 100.0,
            "scenario": {
                "observation_period": {"start_date": "2024-05-01", "end_date": "2024-04-01"}
            },
        },
    ],
)
def test_invalid_payloads_rejected(client, payload):
    assert client.post(URL, json=payload).status_code == 422


@pytest.mark.parametrize(
    "raw",
    [
        '{"observed_total_mm": NaN, "baseline_mean_mm": 100.0}',
        '{"observed_total_mm": Infinity, "baseline_mean_mm": 100.0}',
        '{"observed_total_mm": 1e999, "baseline_mean_mm": 100.0}',
    ],
)
def test_non_finite_json_literals_rejected(client, raw):
    response = client.post(URL, content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail
    assert all({"loc", "msg", "type"} <= set(item) for item in detail)
    assert all("input" not in item for item in detail)


def test_malformed_json_rejected(client):
    response = client.post(URL, content="{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422