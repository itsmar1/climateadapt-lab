"""Request and bundle schemas for the ERA5-Land and environmental-bundle endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BundleIndicatorName = Literal[
    "chirps_spi", "era5_spi", "era5_temperature_anomaly", "era5_soil_moisture_anomaly"
]
ALL_BUNDLE_INDICATORS: tuple[str, ...] = (
    "chirps_spi",
    "era5_spi",
    "era5_temperature_anomaly",
    "era5_soil_moisture_anomaly",
)
SOIL_BUNDLE_VARIABLE = "volumetric_soil_water_layer_1"


class _Era5WindowRequest(BaseModel):
    """Shared window parameters for the ERA5-Land indicator endpoints."""

    model_config = ConfigDict(extra="forbid")

    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]
    target_end_month: str = Field(
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
        description="Last month of the analysis window, formatted YYYY-MM.",
        examples=["2024-03"],
    )
    timescale_months: Annotated[int, Field(strict=True, ge=1, le=48)] = Field(
        description="Accumulation period in months (1-48)."
    )
    reference_start_year: Annotated[int, Field(strict=True, ge=1, le=9999)] = 1991
    reference_end_year: Annotated[int, Field(strict=True, ge=1, le=9999)] = 2020
    min_reference_years: Annotated[int, Field(strict=True, ge=10, le=100)] = Field(
        default=30,
        description="Minimum usable reference years (WMO recommends at least 30).",
    )
    land_fallback_max_km: Annotated[
        float | None, Field(strict=True, gt=0, le=25, allow_inf_nan=False)
    ] = Field(
        default=None,
        description="Opt in: use the nearest valid neighbouring ERA5-Land grid point "
        "within this distance (0-25 km) when the nearest point is masked. Always reported.",
    )

    @model_validator(mode="after")
    def _check_reference_period(self) -> _Era5WindowRequest:
        if self.reference_end_year < self.reference_start_year:
            raise ValueError("reference_end_year must not be earlier than reference_start_year.")
        n_years = self.reference_end_year - self.reference_start_year + 1
        if self.min_reference_years > n_years:
            raise ValueError(
                f"min_reference_years ({self.min_reference_years}) exceeds the number of "
                f"reference years ({n_years})."
            )
        return self


class Era5SpiRequest(_Era5WindowRequest):
    """Request schema for the ERA5-Land SPI endpoint."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "latitude": 30.43,
                "longitude": -9.61,
                "target_end_month": "2024-03",
                "timescale_months": 3,
                "reference_start_year": 1991,
                "reference_end_year": 2020,
                "min_reference_years": 30,
                "land_fallback_max_km": 15.0,
            }
        },
    )


class Era5TemperatureAnomalyRequest(_Era5WindowRequest):
    """Request schema for the ERA5-Land temperature-anomaly endpoint."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "latitude": 30.43,
                "longitude": -9.61,
                "target_end_month": "2024-03",
                "timescale_months": 3,
                "reference_start_year": 1991,
                "reference_end_year": 2020,
                "min_reference_years": 30,
                "land_fallback_max_km": 15.0,
            }
        },
    )


class Era5SoilMoistureAnomalyRequest(_Era5WindowRequest):
    """Request schema for the ERA5-Land soil-moisture-anomaly endpoint."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "latitude": 30.43,
                "longitude": -9.61,
                "target_end_month": "2024-03",
                "timescale_months": 3,
                "variable": "volumetric_soil_water_layer_1",
                "reference_start_year": 1991,
                "reference_end_year": 2020,
                "min_reference_years": 30,
                "land_fallback_max_km": 15.0,
            }
        },
    )

    variable: Literal[
        "volumetric_soil_water_layer_1",
        "volumetric_soil_water_layer_2",
        "volumetric_soil_water_layer_3",
    ] = Field(
        default="volumetric_soil_water_layer_1",
        description="Soil layer (0-7, 7-28, 28-100 cm). Layer 4 is excluded: its "
        "documented depth is contested.",
    )


class EnvironmentalBundleRequest(_Era5WindowRequest):
    """Request schema for the environmental-bundle endpoint.

    The bundle always uses soil layer 1; layers 2-3 are available on the single
    soil-moisture endpoint.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "latitude": 30.43,
                "longitude": -9.61,
                "target_end_month": "2024-03",
                "timescale_months": 3,
                "reference_start_year": 1991,
                "reference_end_year": 2020,
                "min_reference_years": 30,
                "land_fallback_max_km": 15.0,
                "indicators": list(ALL_BUNDLE_INDICATORS),
            }
        },
    )

    indicators: list[BundleIndicatorName] = Field(
        default=list(ALL_BUNDLE_INDICATORS),
        description="Subset to compute; unlisted indicators return status 'skipped'.",
    )


class BundleIndicatorResult(BaseModel):
    """One indicator's outcome inside a bundle. Failures are reported, never hidden."""

    model_config = ConfigDict(extra="forbid")

    indicator: str = Field(description="Indicator name, as in the request selector.")
    status: Literal["ok", "undefined", "failed", "skipped"] = Field(
        description="'ok': computed. 'undefined': computed but indeterminate "
        "(e.g. SPI with no variance). 'failed': error below. 'skipped': not requested."
    )
    error_type: str | None = Field(
        default=None, description="Machine-readable error code (failed only)."
    )
    error_message: str | None = Field(default=None, description="Human-readable cause.")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Full pipeline result (values, provenance, limitations, grid cells).",
    )
    requested_latitude: float
    requested_longitude: float
    grid_point_latitude: float | None = Field(
        default=None, description="Used grid point/cell (null unless computed)."
    )
    grid_point_longitude: float | None = Field(
        default=None, description="Used grid point/cell (null unless computed)."
    )


class EnvironmentalBundleResponse(BaseModel):
    """Per-indicator environmental results. Never a composite score or severity label."""

    model_config = ConfigDict(extra="forbid")

    indicator: Literal["environmental_bundle"] = "environmental_bundle"
    latitude: float
    longitude: float
    target_end_month: str
    timescale_months: int
    reference_start_year: int
    reference_end_year: int
    entries: list[BundleIndicatorResult]
