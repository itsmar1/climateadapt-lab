"""Tool wrappers: thin, typed gates over deterministic functions.

Each tool takes a Pydantic input, calls exactly one deterministic function, and
returns a Pydantic output. The LLM never calls these directly (fixed pipeline),
has no filesystem access, and reaches no network except through the injected
provider in the draft stage. Deterministic functions are imported at module
top so tests can monkeypatch them for failure injection.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from climateadapt.api.bundle import run_environmental_bundle
from climateadapt.data.chirps import ChirpsV3Client
from climateadapt.data.era5_land import Era5LandClient
from climateadapt.data.periods import YearMonth
from climateadapt.llm.validator import ValidationContext, ValidationResult, validate_report
from climateadapt.rag.manifest import Manifest
from climateadapt.rag.models import Chunk, RetrievedChunk
from climateadapt.rag.retrieval import Bm25Retriever, HybridRetriever, Retriever
from climateadapt.recommend.schema import (
    InterventionCatalog,
    RecommendationResponse,
    ScenarioContext,
)
from climateadapt.recommend.service import recommend
from climateadapt.schemas_era5 import (
    ALL_BUNDLE_INDICATORS,
    BundleIndicatorName,
    EnvironmentalBundleResponse,
)


class BundleToolParams(BaseModel):
    """Inputs of ``get_environmental_bundle`` (validated before any fetch)."""

    model_config = ConfigDict(extra="forbid")

    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]
    target_end_month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    timescale_months: Annotated[int, Field(strict=True, ge=1, le=48)]
    reference_start_year: Annotated[int, Field(strict=True, ge=1, le=9999)]
    reference_end_year: Annotated[int, Field(strict=True, ge=1, le=9999)]
    min_reference_years: Annotated[int, Field(strict=True, ge=10, le=100)]
    land_fallback_max_km: Annotated[
        float | None, Field(strict=True, gt=0, le=25, allow_inf_nan=False)
    ] = None
    indicators: list[BundleIndicatorName] = Field(default=list(ALL_BUNDLE_INDICATORS))


class RetrievalToolParams(BaseModel):
    """Inputs of ``retrieve_evidence``."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    top_k: Annotated[int, Field(strict=True, ge=1, le=20)] = 5
    exclude_reference: Annotated[bool, Field(strict=True)] = True


class RetrievalToolResult(BaseModel):
    """Retrieved passages plus which retriever produced them."""

    model_config = ConfigDict(extra="forbid")

    query: str
    retriever: str
    hits: list[RetrievedChunk]


class RankingToolParams(BaseModel):
    """Inputs of ``rank_adaptation_options`` (scenario side; bundle passes through)."""

    model_config = ConfigDict(extra="forbid")

    crop: str | None = Field(default=None, min_length=1, max_length=80)
    has_water_source: Annotated[bool | None, Field(strict=True)] = None
    has_irrigation_equipment: Annotated[bool | None, Field(strict=True)] = None
    production_system: str | None = Field(default=None, pattern=r"^(irrigated|rainfed)$")
    season: str | None = Field(default=None, min_length=1, max_length=40)
    latitude: Annotated[float | None, Field(strict=True, ge=-90, le=90,
                                            allow_inf_nan=False)] = None
    longitude: Annotated[float | None, Field(strict=True, ge=-180, le=180,
                                             allow_inf_nan=False)] = None


def get_environmental_bundle(
    params: BundleToolParams,
    chirps: ChirpsV3Client | None,
    era5: Era5LandClient | None,
) -> EnvironmentalBundleResponse:
    """Run the P05 bundle (per-indicator statuses; failures never hidden)."""
    if chirps is None or era5 is None:
        raise ValueError("get_environmental_bundle needs both climate clients.")
    year, month = params.target_end_month.split("-")
    result = run_environmental_bundle(
        chirps,
        era5,
        latitude=params.latitude,
        longitude=params.longitude,
        target_end_month=YearMonth(int(year), int(month)),
        timescale_months=params.timescale_months,
        reference_start_year=params.reference_start_year,
        reference_end_year=params.reference_end_year,
        min_reference_years=params.min_reference_years,
        land_fallback_max_km=params.land_fallback_max_km,
        indicators=list(params.indicators),
    )
    return EnvironmentalBundleResponse.model_validate(result)


def retrieve_evidence(
    params: RetrievalToolParams,
    chunks: list[Chunk],
    dense_retriever: Retriever | None = None,
) -> RetrievalToolResult:
    """Search the ingested corpus: hybrid when dense is available, else BM25."""
    bm25 = Bm25Retriever(chunks)
    if dense_retriever is None:
        hits = bm25.search(
            params.query, params.top_k, exclude_reference=params.exclude_reference
        )
        return RetrievalToolResult(query=params.query, retriever="bm25", hits=hits)
    hybrid = HybridRetriever([bm25, dense_retriever])
    hits = hybrid.search(
        params.query, params.top_k, exclude_reference=params.exclude_reference
    )
    return RetrievalToolResult(query=params.query, retriever="hybrid", hits=hits)


def rank_adaptation_options(
    params: RankingToolParams,
    bundle: EnvironmentalBundleResponse,
    catalog: InterventionCatalog,
    manifest: Manifest,
    *,
    ingested_doc_ids: set[str] | None = None,
) -> RecommendationResponse:
    """Rank catalog options deterministically (constraints, then scores)."""
    scenario = ScenarioContext.model_validate(params.model_dump())
    return recommend(catalog, scenario, bundle, manifest, ingested_doc_ids=ingested_doc_ids)


def validate_report_tool(draft: dict, ctx: ValidationContext) -> ValidationResult:
    """Validate a model draft (thin wrapper over the P09 validator)."""
    return validate_report(draft, ctx)
