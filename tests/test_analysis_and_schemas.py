import pytest
from pydantic import ValidationError

from climateadapt.analysis import analyze_rainfall
from climateadapt.schemas import (
    AnalysisScenario,
    Location,
    ObservationPeriod,
    RainfallAnalysisRequest,
)


def test_analyze_rainfall_ok():
    response = analyze_rainfall(
        RainfallAnalysisRequest(
            observed_total_mm=80.0, baseline_mean_mm=100.0, data_origin="synthetic_example"
        )
    )
    assert response.status == "ok"
    assert response.percentage_anomaly == pytest.approx(-20.0)
    assert response.absolute_difference_mm == pytest.approx(-20.0)
    assert response.direction == "below_baseline"
    assert response.data_origin == "synthetic_example"
    assert response.message is None
    assert response.limitations


def test_analyze_rainfall_zero_baseline_is_explicitly_undefined():
    response = analyze_rainfall(
        RainfallAnalysisRequest(observed_total_mm=10.0, baseline_mean_mm=0.0)
    )
    assert response.status == "undefined"
    assert response.percentage_anomaly is None
    assert response.message


def test_default_data_origin_is_user_supplied():
    request = RainfallAnalysisRequest(observed_total_mm=1.0, baseline_mean_mm=1.0)
    assert request.data_origin == "user_supplied"


@pytest.mark.parametrize("field", ["observed_total_mm", "baseline_mean_mm"])
def test_negative_values_rejected_by_schema(field):
    payload = {"observed_total_mm": 1.0, "baseline_mean_mm": 1.0, field: -1.0}
    with pytest.raises(ValidationError):
        RainfallAnalysisRequest(**payload)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_rejected_by_schema(bad):
    with pytest.raises(ValidationError):
        RainfallAnalysisRequest(observed_total_mm=bad, baseline_mean_mm=1.0)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        RainfallAnalysisRequest(observed_total_mm=1.0, baseline_mean_mm=1.0, bogus=1)  # type: ignore[call-arg]


@pytest.mark.parametrize(("lat", "lon"), [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_location_bounds(lat, lon):
    with pytest.raises(ValidationError):
        Location(latitude=lat, longitude=lon)


def test_location_valid():
    loc = Location(latitude=30.4, longitude=-9.6)
    assert loc.latitude == 30.4


def test_observation_period_order():
    with pytest.raises(ValidationError):
        ObservationPeriod(start_date="2024-05-01", end_date="2024-04-01")
    period = ObservationPeriod(start_date="2024-03-01", end_date="2024-03-01")
    assert period.start_date == period.end_date


def test_scenario_all_optional():
    assert AnalysisScenario().name is None