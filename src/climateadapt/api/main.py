"""FastAPI application: health check and typed rainfall-analysis endpoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from climateadapt import __version__
from climateadapt.analysis import analyze_rainfall
from climateadapt.config import get_settings
from climateadapt.indicators.rainfall import InvalidPrecipitationError
from climateadapt.schemas import (
    HealthResponse,
    RainfallAnalysisRequest,
    RainfallAnalysisResponse,
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


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="ClimateAdapt Lab API",
        version=__version__,
        description=(
            "Evidence-grounded agricultural drought adaptation decision support. "
            "Milestone 0: prototype rainfall anomaly only; not a drought-severity classifier."
        ),
    )

    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, environment=settings.environment)

    @app.post(
        "/v1/analysis/rainfall-anomaly",
        response_model=RainfallAnalysisResponse,
        tags=["analysis"],
        summary="Prototype precipitation percentage anomaly",
    )
    def rainfall_anomaly(request: RainfallAnalysisRequest) -> RainfallAnalysisResponse:
        try:
            return analyze_rainfall(request)
        except InvalidPrecipitationError as exc:  # defensive: schema should catch these first
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()