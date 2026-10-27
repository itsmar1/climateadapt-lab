"""Request schema for the CHIRPS SPI endpoint."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChirpsSpiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]
    target_end_month: str = Field(
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
        description="Last month of the SPI window, formatted YYYY-MM.",
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

    @model_validator(mode="after")
    def _check_reference_period(self) -> ChirpsSpiRequest:
        if self.reference_end_year < self.reference_start_year:
            raise ValueError("reference_end_year must not be earlier than reference_start_year.")
        n_years = self.reference_end_year - self.reference_start_year + 1
        if self.min_reference_years > n_years:
            raise ValueError(
                f"min_reference_years ({self.min_reference_years}) exceeds the number of "
                f"reference years ({n_years})."
            )
        return self