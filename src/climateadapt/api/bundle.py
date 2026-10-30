"""Environmental bundle assembly: run each indicator, report every outcome.

One indicator's failure never hides the others: each entry carries its own status
(ok / undefined / failed / skipped) plus the result or the machine-readable error.
No composite score is computed and no severity label is added, here or downstream.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from climateadapt.api.errors import JOB_INTERNAL, domain_error_status
from climateadapt.data.chirps import ChirpsV3Client
from climateadapt.data.era5_land import Era5LandClient
from climateadapt.data.periods import YearMonth
from climateadapt.pipelines.soil_moisture_anomaly import era5_land_soil_moisture_anomaly
from climateadapt.pipelines.spi import chirps_spi
from climateadapt.pipelines.spi_era5 import era5_land_spi
from climateadapt.pipelines.temperature_anomaly import era5_land_temperature_anomaly
from climateadapt.schemas_era5 import SOIL_BUNDLE_VARIABLE

logger = logging.getLogger(__name__)


def _entry(
    indicator: str,
    status: str,
    latitude: float,
    longitude: float,
    *,
    result: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    grid_point_latitude: float | None = None,
    grid_point_longitude: float | None = None,
) -> dict[str, Any]:
    return {
        "indicator": indicator,
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "result": result,
        "requested_latitude": latitude,
        "requested_longitude": longitude,
        "grid_point_latitude": grid_point_latitude,
        "grid_point_longitude": grid_point_longitude,
    }


def _run_one(
    indicator: str,
    runner: Callable[[], dict[str, Any]],
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Run one indicator, translating outcomes to a bundle entry (never raises)."""
    try:
        result = runner()
    except Exception as exc:  # every failure becomes a reportable entry
        mapped = domain_error_status(exc)
        if mapped is not None:
            _, code = mapped
            return _entry(
                indicator, "failed", latitude, longitude,
                error_type=code, error_message=str(exc),
            )
        logger.exception("Bundle indicator %s failed unexpectedly", indicator)
        return _entry(
            indicator, "failed", latitude, longitude,
            error_type=JOB_INTERNAL, error_message="Internal indicator error.",
        )
    status = result.get("status", "ok")
    grid_lat = result.get("grid_point_latitude", result.get("grid_cell_center_latitude"))
    grid_lon = result.get("grid_point_longitude", result.get("grid_cell_center_longitude"))
    return _entry(
        indicator, status, latitude, longitude,
        result=result, grid_point_latitude=grid_lat, grid_point_longitude=grid_lon,
    )


def run_environmental_bundle(
    chirps_client: ChirpsV3Client,
    era5_client: Era5LandClient,
    *,
    latitude: float,
    longitude: float,
    target_end_month: YearMonth,
    timescale_months: int,
    reference_start_year: int,
    reference_end_year: int,
    min_reference_years: int,
    land_fallback_max_km: float | None,
    indicators: list[str],
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Compute the requested indicators; each outcome is reported independently."""
    era5_kwargs: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "target_end_month": target_end_month,
        "timescale_months": timescale_months,
        "reference_start_year": reference_start_year,
        "reference_end_year": reference_end_year,
        "min_reference_years": min_reference_years,
        "land_fallback_max_km": land_fallback_max_km,
    }
    chirps_kwargs: dict[str, Any] = {
        key: value for key, value in era5_kwargs.items() if key != "land_fallback_max_km"
    }

    def dump(model: Any) -> dict[str, Any]:
        return model.model_dump(mode="json")

    runners: dict[str, Callable[[], dict[str, Any]]] = {
        "chirps_spi": lambda: dump(chirps_spi(chirps_client, **chirps_kwargs)),
        "era5_spi": lambda: dump(era5_land_spi(era5_client, **era5_kwargs)),
        "era5_temperature_anomaly": lambda: dump(
            era5_land_temperature_anomaly(era5_client, **era5_kwargs)
        ),
        "era5_soil_moisture_anomaly": lambda: dump(
            era5_land_soil_moisture_anomaly(
                era5_client, variable=SOIL_BUNDLE_VARIABLE, **era5_kwargs
            )
        ),
    }

    entries = []
    for position, name in enumerate(runners, start=1):
        if name in indicators:
            entries.append(_run_one(name, runners[name], latitude, longitude))
        else:
            entries.append(_entry(name, "skipped", latitude, longitude))
        if progress is not None:
            progress(position, len(runners))
    return {
        "indicator": "environmental_bundle",
        "latitude": latitude,
        "longitude": longitude,
        "target_end_month": str(target_end_month),
        "timescale_months": timescale_months,
        "reference_start_year": reference_start_year,
        "reference_end_year": reference_end_year,
        "entries": entries,
    }
