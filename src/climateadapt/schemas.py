"""Pydantic schemas for agricultural analysis scenarios and rainfall analysis."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Finite, non-negative millimetre value. Strict mode rejects booleans and numeric strings.
PrecipitationMm = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]

DataOrigin = Literal["synthetic_example", "user_supplied"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(_StrictModel):
    """A point location in WGS84 decimal degrees."""

    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]


class ObservationPeriod(_StrictModel):
    """Inclusive date range of the observed precipitation total."""

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _check_order(self) -> ObservationPeriod:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date.")
        return self


class AnalysisScenario(_StrictModel):
    """Optional descriptive context for an analysis. Informational only in Milestone 0."""

    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    location: Location | None = None
    crop: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    observation_period: ObservationPeriod | None = None
    baseline_description: Annotated[str, Field(max_length=300)] | None = Field(
        default=None,
        description="Free-text description of the baseline, e.g. '1991-2020 mean, Mar-May, "
        "source: <dataset>'. Not validated.",
    )


class RainfallAnalysisRequest(_StrictModel):
    observed_total_mm: PrecipitationMm = Field(
        description="Observed-period precipitation total in millimetres."
    )
    baseline_mean_mm: PrecipitationMm = Field(
        description="Historical baseline mean for the same window, in millimetres."
    )
    data_origin: DataOrigin = Field(
        default="user_supplied",
        description="Declares whether the numbers are a synthetic example or user-supplied.",
    )
    scenario: AnalysisScenario | None = None


class RainfallAnalysisResponse(_StrictModel):
    status: Literal["ok", "undefined"]
    indicator: Literal["precipitation_percentage_anomaly"] = "precipitation_percentage_anomaly"
    percentage_anomaly: float | None = Field(
        description="Anomaly in percent, or null when undefined. Never a placeholder number."
    )
    absolute_difference_mm: float
    direction: Literal["below_baseline", "above_baseline", "equal_to_baseline"]
    observed_total_mm: float
    baseline_mean_mm: float
    formula: str
    data_origin: DataOrigin
    scenario: AnalysisScenario | None = None
    message: str | None = None
    limitations: list[str]


class HealthResponse(_StrictModel):
    status: Literal["ok"]
    version: str
    environment: str