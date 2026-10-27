"""FastAPI application: health, prototype anomaly, CHIRPS anomaly, and CHIRPS SPI."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from climateadapt import __version__
from climateadapt.analysis import analyze_rainfall
from climateadapt.api.dependencies import get_chirps_client
from climateadapt.config import get_settings
from climateadapt.data.chirps import ChirpsV3Client
from climateadapt.data.errors import (
    DataIntegrityError,
    DataNotAvailableError,
    DownloadError,
    MissingDataError,
    OutsideCoverageError,
)
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.rainfall import InvalidPrecipitationError
from climateadapt.indicators.spi import InsufficientReferenceError
from climateadapt.pipelines.rainfall_anomaly import (
    ChirpsRainfallAnomalyResult,
    InsufficientBaselineError,
    chirps_rainfall_anomaly,
)
from climateadapt.pipelines.spi import ChirpsSpiResult, chirps_spi
from climateadapt.schemas import (
    HealthResponse,
    RainfallAnalysisRequest,
    RainfallAnalysisResponse,
)
from climateadapt.schemas_chirps import ChirpsRainfallAnomalyRequest
from climateadapt.schemas_spi import ChirpsSpiRequest

# Domain error -> (HTTP status, machine-readable code). All error bodies share one shape:
# {"detail": [{"loc": [...], "msg": "...", "type": "<code>"}]}
_DOMAIN_ERRORS: list[tuple[type[Exception], int, str]] = [
    (OutsideCoverageError, 422, "outside_coverage"),
    (DataNotAvailableError, 404, "data_not_available"),
    (MissingDataError, 422, "missing_data"),
    (InsufficientBaselineError, 422, "insufficient_baseline"),
    (InsufficientReferenceError, 422, "insufficient_reference"),
    (DownloadError, 502, "download_error"),
    (DataIntegrityError, 502, "data_integrity_error"),
]


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": [{"loc": [], "msg": message, "type": code}]},
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a 422 that never echoes raw input.

    FastAPI's default handler includes the offending input in the body. For values such as
    NaN or Infinity that cannot be serialised as compliant JSON, building the error response
    itself fails and surfaces as a 500. We return only location, message, and error type.
    """
    detail = [
        {
            "loc": list(error.get("loc", ())),
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


def _register_domain_errors(app: FastAPI) -> None:
    for exc_type, status_code, code in _DOMAIN_ERRORS:

        async def handler(
            request: Request,
            exc: Exception,
            _status: int = status_code,
            _code: str = code,
        ) -> JSONResponse:
            return _error_response(_status, _code, str(exc))

        app.add_exception_handler(exc_type, handler)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="ClimateAdapt Lab API",
        version=__version__,
        description=(
            "Evidence-grounded agricultural drought adaptation decision support. "
            "Indicators are precipitation-only (percentage anomaly, SPI); they describe "
            "rainfall relative to a reference period and do not measure drought impact or "
            "classify severity."
        ),
    )

    app.add_exception_handler(RequestValidationError, validation_error_handler)
    _register_domain_errors(app)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, environment=settings.environment)

    @app.post(
        "/v1/analysis/rainfall-anomaly",
        response_model=RainfallAnalysisResponse,
        tags=["analysis"],
        summary="Prototype precipitation percentage anomaly from user-supplied totals",
    )
    def rainfall_anomaly(request: RainfallAnalysisRequest) -> RainfallAnalysisResponse:
        try:
            return analyze_rainfall(request)
        except InvalidPrecipitationError as exc:  # defensive: schema should catch these first
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/v1/analysis/chirps-rainfall-anomaly",
        response_model=ChirpsRainfallAnomalyResult,
        tags=["analysis"],
        summary="Precipitation percentage anomaly computed from CHIRPS v3 Final",
        description=(
            "Compares the observed calendar-month window total with the mean of the same "
            "window over the baseline years, at the CHIRPS grid cell containing the point. "
            "The first request for a period reads many monthly values and may be slow; "
            "later requests use the local cache. Not a drought-severity classification."
        ),
    )
    def chirps_rainfall_anomaly_endpoint(
        request: ChirpsRainfallAnomalyRequest,
        client: Annotated[ChirpsV3Client, Depends(get_chirps_client)],
    ) -> ChirpsRainfallAnomalyResult:
        return chirps_rainfall_anomaly(
            client,
            latitude=request.latitude,
            longitude=request.longitude,
            observed_start=YearMonth.parse(request.observed_start_month),
            window_months_count=request.window_months,
            baseline_start_year=request.baseline_start_year,
            baseline_end_year=request.baseline_end_year,
        )

    @app.post(
        "/v1/analysis/chirps-spi",
        response_model=ChirpsSpiResult,
        tags=["analysis"],
        summary="Standardized Precipitation Index (SPI) from CHIRPS v3 Final",
        description=(
            "SPI for the window ending at target_end_month, calibrated on the reference "
            "period (gamma distribution per calendar month; WMO-No. 1090). Precipitation "
            "only: it does not measure agricultural drought impact and no severity labels "
            "are returned. A cold request reads about timescale x reference-years monthly "
            "values and may take a minute or more."
        ),
    )
    def chirps_spi_endpoint(
        request: ChirpsSpiRequest,
        client: Annotated[ChirpsV3Client, Depends(get_chirps_client)],
    ) -> ChirpsSpiResult:
        return chirps_spi(
            client,
            latitude=request.latitude,
            longitude=request.longitude,
            target_end_month=YearMonth.parse(request.target_end_month),
            timescale_months=request.timescale_months,
            reference_start_year=request.reference_start_year,
            reference_end_year=request.reference_end_year,
            min_reference_years=request.min_reference_years,
        )

    return app


app = create_app()