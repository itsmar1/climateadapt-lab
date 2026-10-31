"""FastAPI application: health, prototype anomaly, CHIRPS + ERA5 analyses, and jobs.

CHIRPS endpoints answer synchronously (historical behavior, warm cache is fast).
ERA5-Land endpoints and the environmental bundle run as background jobs: POST returns
202 + job id immediately, and clients poll GET /v1/jobs/{id}. No new endpoint blocks
past its own request/response round trip.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from climateadapt import __version__
from climateadapt.agent.schemas import AgentConfig, AgentDeps, AgentScenario
from climateadapt.analysis import analyze_rainfall
from climateadapt.api.body_limit import BodyLimitMiddleware
from climateadapt.api.bundle import run_environmental_bundle
from climateadapt.api.dependencies import (
    close_shared_clients,
    get_agent_deps,
    get_chirps_client,
    get_era5_client,
    get_job_store,
    get_llm_provider,
    get_scenario_store,
)
from climateadapt.api.errors import (
    DOMAIN_ERRORS,
    JOB_NOT_FOUND,
    SCENARIO_NOT_FOUND,
    JobStoreFullError,
)
from climateadapt.api.jobs import JobStatus, JobStore, JobSubmitted
from climateadapt.api.scenarios import run_scenario_job, to_detail, to_summary
from climateadapt.api.schemas_scenarios import (
    ScenarioCreated,
    ScenarioDetail,
    ScenarioList,
)
from climateadapt.api.store import ScenarioStore
from climateadapt.config import get_settings
from climateadapt.data.chirps import ChirpsV3Client
from climateadapt.data.era5_land import Era5LandClient
from climateadapt.data.periods import YearMonth
from climateadapt.indicators.rainfall import InvalidPrecipitationError
from climateadapt.llm.provider import LLMProvider
from climateadapt.pipelines.rainfall_anomaly import (
    ChirpsRainfallAnomalyResult,
    chirps_rainfall_anomaly,
)
from climateadapt.pipelines.soil_moisture_anomaly import era5_land_soil_moisture_anomaly
from climateadapt.pipelines.spi import ChirpsSpiResult, chirps_spi
from climateadapt.pipelines.spi_era5 import era5_land_spi
from climateadapt.pipelines.temperature_anomaly import era5_land_temperature_anomaly
from climateadapt.schemas import (
    HealthResponse,
    RainfallAnalysisRequest,
    RainfallAnalysisResponse,
)
from climateadapt.schemas_chirps import ChirpsRainfallAnomalyRequest
from climateadapt.schemas_era5 import (
    EnvironmentalBundleRequest,
    Era5SoilMoistureAnomalyRequest,
    Era5SpiRequest,
    Era5TemperatureAnomalyRequest,
)
from climateadapt.schemas_spi import ChirpsSpiRequest


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
    for exc_type, status_code, code in DOMAIN_ERRORS:

        async def handler(
            request: Request,
            exc: Exception,
            _status: int = status_code,
            _code: str = code,
        ) -> JSONResponse:
            return _error_response(_status, _code, str(exc))

        app.add_exception_handler(exc_type, handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_shared_clients()


def _submit(label: str, total_steps: int, jobs: JobStore, fn: Any) -> JobSubmitted:
    job_id = jobs.submit(label, total_steps, fn)
    return JobSubmitted(job_id=job_id, status="queued", status_url=f"/v1/jobs/{job_id}")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="ClimateAdapt Lab API",
        version=__version__,
        description=(
            "Evidence-grounded agricultural drought adaptation decision support. "
            "Indicators describe rainfall, temperature, and soil moisture relative to "
            "reference periods; they do not measure drought impact or classify severity."
        ),
        lifespan=lifespan,
    )
    # Body limit first = runs inside CORS, so 413s still carry CORS headers.
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.api_max_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
        max_age=600,
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

    @app.post(
        "/v1/analysis/era5-spi",
        response_model=JobSubmitted,
        status_code=202,
        tags=["analysis"],
        summary="Standardized Precipitation Index (SPI) from ERA5-Land (background job)",
        description=(
            "Queues an ERA5-Land SPI computation and returns 202 + job id immediately; "
            "poll GET /v1/jobs/{job_id} for the result. Gamma fit per calendar month "
            "(WMO-No. 1090); no severity labels. Cold CDS requests take minutes."
        ),
    )
    def era5_spi_endpoint(
        request: Era5SpiRequest,
        client: Annotated[Era5LandClient, Depends(get_era5_client)],
        jobs: Annotated[JobStore, Depends(get_job_store)],
    ) -> JobSubmitted:
        params = {
            "latitude": request.latitude,
            "longitude": request.longitude,
            "target_end_month": YearMonth.parse(request.target_end_month),
            "timescale_months": request.timescale_months,
            "reference_start_year": request.reference_start_year,
            "reference_end_year": request.reference_end_year,
            "min_reference_years": request.min_reference_years,
            "land_fallback_max_km": request.land_fallback_max_km,
        }
        return _submit(
            "era5_spi", 1, jobs,
            lambda progress: era5_land_spi(client, **params).model_dump(mode="json"),
        )

    @app.post(
        "/v1/analysis/era5-temperature-anomaly",
        response_model=JobSubmitted,
        status_code=202,
        tags=["analysis"],
        summary="Temperature window anomaly from ERA5-Land (background job)",
        description=(
            "Queues an ERA5-Land temperature-anomaly computation and returns 202 + job id "
            "immediately; poll GET /v1/jobs/{job_id} for the result. Day-weighted window "
            "means in degC with standardized anomaly and percentile rank. Cold CDS "
            "requests take minutes."
        ),
    )
    def era5_temperature_anomaly_endpoint(
        request: Era5TemperatureAnomalyRequest,
        client: Annotated[Era5LandClient, Depends(get_era5_client)],
        jobs: Annotated[JobStore, Depends(get_job_store)],
    ) -> JobSubmitted:
        params = {
            "latitude": request.latitude,
            "longitude": request.longitude,
            "target_end_month": YearMonth.parse(request.target_end_month),
            "timescale_months": request.timescale_months,
            "reference_start_year": request.reference_start_year,
            "reference_end_year": request.reference_end_year,
            "min_reference_years": request.min_reference_years,
            "land_fallback_max_km": request.land_fallback_max_km,
        }
        return _submit(
            "era5_temperature_anomaly", 1, jobs,
            lambda progress: era5_land_temperature_anomaly(
                client, **params
            ).model_dump(mode="json"),
        )

    @app.post(
        "/v1/analysis/era5-soil-moisture-anomaly",
        response_model=JobSubmitted,
        status_code=202,
        tags=["analysis"],
        summary="Soil-moisture window anomaly from ERA5-Land (background job)",
        description=(
            "Queues an ERA5-Land soil-moisture-anomaly computation (layers 1-3) and "
            "returns 202 + job id immediately; poll GET /v1/jobs/{job_id} for the result. "
            "Values in m3/m3 with standardized anomaly; anomalies only, no category "
            "labels. Cold CDS requests take minutes."
        ),
    )
    def era5_soil_moisture_anomaly_endpoint(
        request: Era5SoilMoistureAnomalyRequest,
        client: Annotated[Era5LandClient, Depends(get_era5_client)],
        jobs: Annotated[JobStore, Depends(get_job_store)],
    ) -> JobSubmitted:
        params = {
            "variable": request.variable,
            "latitude": request.latitude,
            "longitude": request.longitude,
            "target_end_month": YearMonth.parse(request.target_end_month),
            "timescale_months": request.timescale_months,
            "reference_start_year": request.reference_start_year,
            "reference_end_year": request.reference_end_year,
            "min_reference_years": request.min_reference_years,
            "land_fallback_max_km": request.land_fallback_max_km,
        }
        return _submit(
            "era5_soil_moisture_anomaly", 1, jobs,
            lambda progress: era5_land_soil_moisture_anomaly(
                client, **params
            ).model_dump(mode="json"),
        )

    @app.post(
        "/v1/analysis/environmental-bundle",
        response_model=JobSubmitted,
        status_code=202,
        tags=["analysis"],
        summary="Per-indicator environmental bundle: CHIRPS SPI + ERA5 trio (job)",
        description=(
            "Queues one bundle run over CHIRPS SPI, ERA5-Land SPI, temperature anomaly "
            "and soil-moisture anomaly (layer 1) and returns 202 + job id immediately; "
            "poll GET /v1/jobs/{job_id} for the result. Each indicator reports its own "
            "status (ok / undefined / failed / skipped) with result or error type, "
            "provenance, limitations, and coordinates. Failures are never hidden, never "
            "merged into a composite score, and never labelled by severity."
        ),
    )
    def environmental_bundle_endpoint(
        request: EnvironmentalBundleRequest,
        chirps_client: Annotated[ChirpsV3Client, Depends(get_chirps_client)],
        era5_client: Annotated[Era5LandClient, Depends(get_era5_client)],
        jobs: Annotated[JobStore, Depends(get_job_store)],
    ) -> JobSubmitted:
        target_end = YearMonth.parse(request.target_end_month)
        return _submit(
            "environmental_bundle", len(request.indicators), jobs,
            lambda progress: run_environmental_bundle(
                chirps_client,
                era5_client,
                latitude=request.latitude,
                longitude=request.longitude,
                target_end_month=target_end,
                timescale_months=request.timescale_months,
                reference_start_year=request.reference_start_year,
                reference_end_year=request.reference_end_year,
                min_reference_years=request.min_reference_years,
                land_fallback_max_km=request.land_fallback_max_km,
                indicators=list(request.indicators),
                progress=progress,
            ),
        )

    @app.get(
        "/v1/jobs/{job_id}",
        response_model=JobStatus,
        tags=["jobs"],
        summary="Poll a background job for status, progress, result, or error",
        description=(
            "Returns the job snapshot: queued / running / succeeded / failed / timed_out, "
            "step progress, and the result or typed error once terminal. Unknown or "
            "TTL-expired ids return 404 (job_not_found)."
        ),
    )
    def job_status_endpoint(
        job_id: str, jobs: Annotated[JobStore, Depends(get_job_store)]
    ) -> JobStatus | JSONResponse:
        snapshot = jobs.get(job_id)
        if snapshot is None:
            return _error_response(404, JOB_NOT_FOUND, "Unknown or expired job id.")
        return JobStatus.model_validate(snapshot)

    @app.post(
        "/v1/scenarios",
        response_model=ScenarioCreated,
        status_code=202,
        tags=["scenarios"],
        summary="Create a scenario: run the agent pipeline as a background job",
        description=(
            "Validates the scenario, persists it, queues one bounded agent run "
            "(bundle, retrieval, ranking, draft, validate), and returns 202 with "
            "the scenario and job ids. Poll GET /v1/scenarios/{id} for the stored "
            "bundle, ranking, report, and trace. No authentication in this demo "
            "API. A full job store returns 503 (server_busy)."
        ),
    )
    def create_scenario_endpoint(
        request: AgentScenario,
        jobs: Annotated[JobStore, Depends(get_job_store)],
        store: Annotated[ScenarioStore, Depends(get_scenario_store)],
        deps: Annotated[AgentDeps, Depends(get_agent_deps)],
        provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    ) -> ScenarioCreated:
        scenario_id = uuid.uuid4().hex
        store.create(scenario_id, "", request.model_dump(mode="json"))
        # Keep the agent's own clock inside the job clock so a timeout lands on
        # the scenario row (partial/failed) instead of only on the job snapshot.
        agent_timeout = min(600.0, max(60.0, jobs.timeout_seconds - 5.0))
        try:
            job_id = jobs.submit(
                "scenario", 1,
                run_scenario_job(
                    scenario_id,
                    store=store,
                    deps=deps,
                    provider=provider,
                    config=AgentConfig(total_timeout_seconds=agent_timeout),
                ),
            )
        except JobStoreFullError:
            store.delete(scenario_id)
            raise
        store.set_job_id(scenario_id, job_id)
        return ScenarioCreated(
            scenario_id=scenario_id,
            job_id=job_id,
            status="queued",
            status_url=f"/v1/jobs/{job_id}",
            scenario_url=f"/v1/scenarios/{scenario_id}",
        )

    @app.get(
        "/v1/scenarios",
        response_model=ScenarioList,
        tags=["scenarios"],
        summary="List stored scenarios, newest first (paginated)",
    )
    def list_scenarios_endpoint(
        store: Annotated[ScenarioStore, Depends(get_scenario_store)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ScenarioList:
        total, rows = store.list_recent(limit, offset)
        return ScenarioList(
            total=total,
            limit=limit,
            offset=offset,
            items=[to_summary(row) for row in rows],
        )

    @app.get(
        "/v1/scenarios/{scenario_id}",
        response_model=ScenarioDetail,
        tags=["scenarios"],
        summary="Retrieve one scenario with bundle, ranking, report, and trace",
        description=(
            "While the run is queued/running, outputs are null. Terminal runs "
            "carry the deterministic bundle and ranking plus either the validated "
            "report (complete) or the labelled fallback (partial), with problems "
            "and warnings explaining why. Unknown ids return 404 "
            "(scenario_not_found)."
        ),
    )
    def get_scenario_endpoint(
        scenario_id: str, store: Annotated[ScenarioStore, Depends(get_scenario_store)]
    ) -> ScenarioDetail | JSONResponse:
        row = store.get(scenario_id)
        if row is None:
            return _error_response(404, SCENARIO_NOT_FOUND, "Unknown scenario id.")
        return to_detail(row)

    @app.delete(
        "/v1/scenarios/{scenario_id}",
        status_code=204,
        tags=["scenarios"],
        summary="Delete a stored scenario (a running job is left to finish unseen)",
        description=(
            "Removes the scenario row; a still-running worker discards its result. "
            "Unknown ids return 404 (scenario_not_found)."
        ),
    )
    def delete_scenario_endpoint(
        scenario_id: str, store: Annotated[ScenarioStore, Depends(get_scenario_store)]
    ) -> Response:
        if not store.delete(scenario_id):
            return _error_response(404, SCENARIO_NOT_FOUND, "Unknown scenario id.")
        return Response(status_code=204)

    return app


app = create_app()
