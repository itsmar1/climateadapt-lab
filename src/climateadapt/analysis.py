"""Service layer joining validated schemas to deterministic indicator functions.

Future components (e.g. the agent) should call this layer rather than the HTTP API.
"""

from __future__ import annotations

from climateadapt.indicators.rainfall import (
    FORMULA,
    LIMITATIONS,
    AnomalyUndefinedError,
    anomaly_direction,
    percentage_anomaly,
)
from climateadapt.schemas import RainfallAnalysisRequest, RainfallAnalysisResponse


def analyze_rainfall(request: RainfallAnalysisRequest) -> RainfallAnalysisResponse:
    """Compute the prototype rainfall anomaly for a validated request.

    An undefined anomaly (zero baseline) is reported explicitly with status 'undefined'
    and a null value, never as a misleading number.
    """
    observed = request.observed_total_mm
    baseline = request.baseline_mean_mm

    anomaly: float | None
    message: str | None
    try:
        anomaly = percentage_anomaly(observed, baseline)
        status = "ok"
        message = None
    except AnomalyUndefinedError as exc:
        anomaly = None
        status = "undefined"
        message = str(exc)

    return RainfallAnalysisResponse(
        status=status,
        percentage_anomaly=anomaly,
        absolute_difference_mm=observed - baseline,
        direction=anomaly_direction(observed, baseline),
        observed_total_mm=observed,
        baseline_mean_mm=baseline,
        formula=FORMULA,
        data_origin=request.data_origin,
        scenario=request.scenario,
        message=message,
        limitations=list(LIMITATIONS),
    )