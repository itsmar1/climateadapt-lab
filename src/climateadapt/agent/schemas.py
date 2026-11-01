"""Agent input, configuration, and dependency models.

The agent is a FIXED sequential pipeline (see ``docs/AGENT_WORKFLOW.md`` for the
recorded LangGraph decision): deterministic Python runs every stage in order,
and the LLM only drafts the report narrative inside the P09 draft/validate
envelope. All inputs are validated before any work starts (fail fast).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from climateadapt.data.chirps import ChirpsV3Client
from climateadapt.data.era5_land import Era5LandClient
from climateadapt.rag.manifest import Manifest
from climateadapt.rag.models import Chunk, Page
from climateadapt.rag.retrieval import Retriever
from climateadapt.recommend.schema import InterventionCatalog
from climateadapt.schemas_era5 import ALL_BUNDLE_INDICATORS, BundleIndicatorName

AGENT_VERSION = 1
"""Version of the fixed pipeline (recorded on every trace)."""


class AgentScenario(BaseModel):
    """One end-to-end run request: where/when, what to retrieve, whose options."""

    model_config = ConfigDict(extra="forbid")

    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]
    target_end_month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    timescale_months: Annotated[int, Field(strict=True, ge=1, le=48)]
    reference_start_year: Annotated[int, Field(strict=True, ge=1, le=9999)] = 1991
    reference_end_year: Annotated[int, Field(strict=True, ge=1, le=9999)] = 2020
    min_reference_years: Annotated[int, Field(strict=True, ge=10, le=100)] = 30
    land_fallback_max_km: Annotated[
        float | None, Field(strict=True, gt=0, le=25, allow_inf_nan=False)
    ] = None
    indicators: list[BundleIndicatorName] = Field(default=list(ALL_BUNDLE_INDICATORS))
    query: str = Field(min_length=1, max_length=500)
    top_k: Annotated[int, Field(strict=True, ge=1, le=20)] = 5
    exclude_reference: Annotated[bool, Field(strict=True)] = True
    crop: str | None = Field(default=None, min_length=1, max_length=80)
    has_water_source: Annotated[bool | None, Field(strict=True)] = None
    has_irrigation_equipment: Annotated[bool | None, Field(strict=True)] = None
    production_system: str | None = Field(default=None, pattern=r"^(irrigated|rainfed)$")
    season: str | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode="after")
    def _check_reference_period(self) -> AgentScenario:
        if self.reference_end_year < self.reference_start_year:
            raise ValueError("reference_end_year must not be earlier than reference_start_year.")
        n_years = self.reference_end_year - self.reference_start_year + 1
        if self.min_reference_years > n_years:
            raise ValueError(
                f"min_reference_years ({self.min_reference_years}) exceeds the number of "
                f"reference years ({n_years})."
            )
        if len(set(self.indicators)) != len(self.indicators):
            raise ValueError("indicators holds duplicates.")
        return self


class AgentConfig(BaseModel):
    """Hard execution limits and LLM settings (all recorded on the trace)."""

    model_config = ConfigDict(extra="forbid")

    max_steps: Annotated[int, Field(strict=True, ge=1)] = 32
    max_tool_calls: Annotated[int, Field(strict=True, ge=1)] = 16
    max_llm_calls: Annotated[int, Field(strict=True, ge=1)] = 1
    max_repair_attempts: Annotated[int, Field(strict=True, ge=0, le=1)] = 0
    token_budget: Annotated[int, Field(strict=True, ge=1)] = 100000
    total_timeout_seconds: Annotated[float, Field(gt=0)] = 600.0
    llm_timeout_seconds: Annotated[float, Field(gt=0)] = 180.0
    temperature: Annotated[float | None, Field(ge=0.0, le=2.0)] = None
    max_tokens: Annotated[int, Field(strict=True, ge=1024, le=32000)] = 16000


@dataclass
class AgentDeps:
    """Data dependencies injected into the workflow (no globals, no network).

    Clients are ``None`` only in tests that stub the bundle tool; the real
    tool raises a clear error when a client it needs is missing.
    """

    chirps: ChirpsV3Client | None = None
    era5: Era5LandClient | None = None
    chunks: list[Chunk] = field(default_factory=list)
    manifest: Manifest | None = None
    pages_by_doc: dict[str, list[Page]] = field(default_factory=dict)
    catalog: InterventionCatalog | None = None
    dense_retriever: Retriever | None = None
