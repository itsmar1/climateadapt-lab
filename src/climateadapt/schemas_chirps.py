"""Request schema for the CHIRPS rainfall-anomaly endpoint."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChirpsRainfallAnomalyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]
    observed_start_month: str = Field(
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
        description="First month of the observation window, formatted YYYY-MM.",
    )
    window_months: Annotated[int, Field(strict=True, ge=1, le=12)] = Field(
        description="Number of whole calendar months in the window (may cross a year end)."
    )
    baseline_start_year: Annotated[int, Field(strict=True, ge=1, le=9999)]
    baseline_end_year: Annotated[int, Field(strict=True, ge=1, le=9999)]

    @model_validator(mode="after")
    def _check_baseline_order(self) -> ChirpsRainfallAnomalyRequest:
        if self.baseline_end_year < self.baseline_start_year:
            raise ValueError("baseline_end_year must not be earlier than baseline_start_year.")
        return self