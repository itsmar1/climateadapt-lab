"""Schemas for the deterministic intervention catalog and recommendation outputs.

The catalog is versioned data: every applicability attribute can be unknown
(``None``), and benefit/cost/risk stay the literal ``"unknown"`` unless a cited
source states them. No LLM is involved here and nothing invents efficacy, cost
or benefit figures.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from climateadapt.schemas_era5 import ALL_BUNDLE_INDICATORS

CATALOG_VERSION = 1
"""Current catalog schema/data version. The loader only accepts this version."""

UNKNOWN = "unknown"
"""Exact marker for an unknown benefit, cost or risk value."""

INTERVENTION_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{2,60}$"

ProductionSystem = Literal["irrigated", "rainfed"]
EvidenceStatus = Literal["supported", "needs_evidence"]
InterventionCategory = Literal[
    "irrigation", "soil_management", "crop_management", "planning", "other"
]

NonEmptyStr = Annotated[str, Field(min_length=1, max_length=80)]
StrictBoolOrUnknown = Annotated[bool | None, Field(strict=True)]
StrictIntList = list[Annotated[int, Field(strict=True, ge=0)]]


class EvidenceLink(BaseModel):
    """One traceable pointer: manifest document + PDF page + short locator.

    ``reference`` is a brief topic locator (not a quote and never a claim).
    """

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=3, max_length=90)
    pdf_page: Annotated[int, Field(strict=True, ge=1)]
    reference: str = Field(min_length=5, max_length=160)


class Applicability(BaseModel):
    """Where an intervention applies. Every attribute may be ``None`` (unknown)."""

    model_config = ConfigDict(extra="forbid")

    crop_types: list[NonEmptyStr] | None = Field(default=None, min_length=1)
    requires_water_source: StrictBoolOrUnknown = None
    production_systems: list[ProductionSystem] | None = Field(default=None, min_length=1)
    soil_types: list[NonEmptyStr] | None = Field(default=None, min_length=1)
    climate_regimes: list[NonEmptyStr] | None = Field(default=None, min_length=1)
    farm_scales: list[NonEmptyStr] | None = Field(default=None, min_length=1)


class Intervention(BaseModel):
    """One catalog entry. Non-``"unknown"`` benefit/cost/risk must cite evidence."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str = Field(pattern=INTERVENTION_ID_PATTERN)
    name: str = Field(min_length=3, max_length=120)
    category: InterventionCategory
    description: str = Field(min_length=10, max_length=600)
    applicability: Applicability
    benefit: str = Field(min_length=1, max_length=280)
    benefit_evidence: StrictIntList = Field(default_factory=list)
    cost: str = Field(min_length=1, max_length=280)
    cost_evidence: StrictIntList = Field(default_factory=list)
    risk: str = Field(min_length=1, max_length=280)
    risk_evidence: StrictIntList = Field(default_factory=list)
    evidence_status: EvidenceStatus
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    expected_sources: list[NonEmptyStr] = Field(default_factory=list)
    needs_evidence_note: str | None = Field(default=None, max_length=300)
    relevant_indicators: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_evidence_consistency(self) -> Intervention:
        if self.evidence_status == "supported":
            if not self.evidence_links:
                raise ValueError("evidence_status 'supported' needs at least one evidence link.")
            if self.needs_evidence_note is not None:
                raise ValueError("needs_evidence_note must be null when status is 'supported'.")
            if self.expected_sources:
                raise ValueError("expected_sources must be empty when status is 'supported'.")
        else:
            if self.evidence_links:
                raise ValueError(
                    "status 'needs_evidence' must not carry evidence links; "
                    "list candidate documents in expected_sources instead."
                )
            if self.needs_evidence_note is None or len(self.needs_evidence_note.strip()) < 10:
                raise ValueError("status 'needs_evidence' needs a needs_evidence_note.")
        pairs = [(link.doc_id, link.pdf_page) for link in self.evidence_links]
        if len(set(pairs)) != len(pairs):
            raise ValueError("evidence_links holds duplicate (doc_id, pdf_page) pairs.")
        for field in ("benefit", "cost", "risk"):
            value: str = getattr(self, field)
            refs: list[int] = getattr(self, f"{field}_evidence")
            if value == UNKNOWN:
                if refs:
                    raise ValueError(f"{field} is 'unknown' but {field}_evidence is not empty.")
            else:
                if not refs:
                    raise ValueError(
                        f"{field} states a value without evidence; keep it 'unknown' "
                        "or cite evidence_links indices."
                    )
                if any(i >= len(self.evidence_links) for i in refs):
                    raise ValueError(f"{field}_evidence indexes out of range for evidence_links.")
                if len(set(refs)) != len(refs):
                    raise ValueError(f"{field}_evidence holds duplicate indices.")
        if len(set(self.relevant_indicators)) != len(self.relevant_indicators):
            raise ValueError("relevant_indicators holds duplicates.")
        unknown = set(self.relevant_indicators) - set(ALL_BUNDLE_INDICATORS)
        if unknown:
            raise ValueError(f"relevant_indicators not in the bundle schema: {sorted(unknown)}")
        return self


class InterventionCatalog(BaseModel):
    """Versioned catalog. Only ``CATALOG_VERSION`` is accepted."""

    model_config = ConfigDict(extra="forbid")

    catalog_version: Annotated[int, Field(strict=True)]
    description: str = Field(min_length=10, max_length=600)
    interventions: list[Intervention] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_version_and_ids(self) -> InterventionCatalog:
        if self.catalog_version != CATALOG_VERSION:
            raise ValueError(
                f"catalog_version {self.catalog_version} is not supported; "
                f"expected {CATALOG_VERSION}."
            )
        ids = [entry.intervention_id for entry in self.interventions]
        if len(set(ids)) != len(ids):
            raise ValueError("interventions holds duplicate intervention_id values.")
        return self


class ScenarioContext(BaseModel):
    """Scenario inputs. Every field may be unknown (``None``).

    ``season`` and the location are accepted and echoed but no v1 hard
    constraint uses them; location matters through the environmental bundle.
    """

    model_config = ConfigDict(extra="forbid")

    crop: str | None = Field(default=None, min_length=1, max_length=80)
    has_water_source: StrictBoolOrUnknown = None
    has_irrigation_equipment: StrictBoolOrUnknown = None
    production_system: ProductionSystem | None = None
    season: str | None = Field(default=None, min_length=1, max_length=40)
    latitude: Annotated[float | None, Field(strict=True, ge=-90, le=90,
                                            allow_inf_nan=False)] = None
    longitude: Annotated[float | None, Field(strict=True, ge=-180, le=180,
                                             allow_inf_nan=False)] = None


class EvidenceReference(BaseModel):
    """A catalog evidence link resolved against the manifest (no invented fields)."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    pdf_page: int
    reference: str
    citation: str
    landing_url: str
    license: str
    license_status: str
    unverified_fields: list[str]


class ExclusionReason(BaseModel):
    """One machine-readable exclusion reason (``code``) with a human message."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class RankedOption(BaseModel):
    """A ranked intervention with its full score breakdown and unknowns."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str
    name: str
    category: InterventionCategory
    score_total: float = Field(ge=0.0, le=1.0)
    score_components: dict[str, float]
    score_weights: dict[str, float]
    score_inputs: dict[str, Any]
    unknowns: list[str]
    evidence: list[EvidenceReference]
    benefit: str
    cost: str
    risk: str


class ExcludedOption(BaseModel):
    """An ineligible intervention with machine-readable reasons."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: str
    name: str
    category: InterventionCategory
    evidence_status: EvidenceStatus
    reasons: list[ExclusionReason] = Field(min_length=1)


class RecommendationResponse(BaseModel):
    """Ranked options, exclusions, unknowns, evidence, warnings and limitations."""

    model_config = ConfigDict(extra="forbid")

    catalog_version: int
    scenario: ScenarioContext
    ranked: list[RankedOption]
    excluded: list[ExcludedOption]
    warnings: list[str]
    limitations: list[str] = Field(min_length=1)
