"""Deterministic hard constraints for the intervention catalog.

Each intervention is either eligible or excluded with machine-readable reasons.
Unknowns never exclude: when a required fact is unknown on either side, the
option stays eligible and the unknown is recorded explicitly. Checks run in a
fixed order and every applicable reason is reported.
"""

from __future__ import annotations

from dataclasses import dataclass

from climateadapt.recommend.schema import (
    ExclusionReason,
    Intervention,
    InterventionCatalog,
    ScenarioContext,
)

NEEDS_EVIDENCE = "needs_evidence"
NO_WATER_SOURCE = "no_water_source"
NO_IRRIGATION_EQUIPMENT = "no_irrigation_equipment"
PRODUCTION_SYSTEM_MISMATCH = "production_system_mismatch"
CROP_NOT_APPLICABLE = "crop_not_applicable"

REASON_MESSAGES = {
    NEEDS_EVIDENCE: "Entry is marked needs_evidence: no ingested corpus evidence backs it.",
    NO_WATER_SOURCE: "Entry requires a water source but the scenario has none.",
    NO_IRRIGATION_EQUIPMENT: "Irrigation entry but the scenario has no irrigation equipment.",
    PRODUCTION_SYSTEM_MISMATCH: "Scenario production system is outside the entry's scope.",
    CROP_NOT_APPLICABLE: "Scenario crop is outside the entry's crop scope.",
}

WATER_SOURCE_UNKNOWN = "water_source_unknown"
IRRIGATION_EQUIPMENT_UNKNOWN = "irrigation_equipment_unknown"
PRODUCTION_SYSTEM_UNKNOWN = "production_system_unknown"
CROP_UNKNOWN = "crop_unknown"
CATALOG_CROP_SCOPE_UNKNOWN = "catalog_crop_scope_unknown"
CATALOG_WATER_REQUIREMENT_UNKNOWN = "catalog_water_requirement_unknown"
CATALOG_PRODUCTION_SCOPE_UNKNOWN = "catalog_production_scope_unknown"
CATALOG_SOIL_SCOPE_UNKNOWN = "catalog_soil_scope_unknown"
CATALOG_CLIMATE_SCOPE_UNKNOWN = "catalog_climate_scope_unknown"
CATALOG_SCALE_SCOPE_UNKNOWN = "catalog_scale_scope_unknown"
BENEFIT_UNKNOWN = "benefit_unknown"
COST_UNKNOWN = "cost_unknown"
RISK_UNKNOWN = "risk_unknown"


@dataclass(frozen=True)
class ConstraintResult:
    """Eligibility verdict for one intervention (catalog order is kept by callers)."""

    intervention_id: str
    eligible: bool
    reasons: tuple[ExclusionReason, ...]
    unknowns: tuple[str, ...]


def _reason(code: str) -> ExclusionReason:
    return ExclusionReason(code=code, message=REASON_MESSAGES[code])


def evaluate(entry: Intervention, scenario: ScenarioContext) -> ConstraintResult:
    """Apply every hard constraint to one entry."""
    reasons: list[ExclusionReason] = []
    unknowns: list[str] = []
    app = entry.applicability

    if entry.evidence_status != "supported":
        reasons.append(_reason(NEEDS_EVIDENCE))

    if app.requires_water_source is True:
        if scenario.has_water_source is False:
            reasons.append(_reason(NO_WATER_SOURCE))
        elif scenario.has_water_source is None:
            unknowns.append(WATER_SOURCE_UNKNOWN)
    elif app.requires_water_source is None:
        unknowns.append(CATALOG_WATER_REQUIREMENT_UNKNOWN)

    if entry.category == "irrigation":
        if scenario.has_irrigation_equipment is False:
            reasons.append(_reason(NO_IRRIGATION_EQUIPMENT))
        elif scenario.has_irrigation_equipment is None:
            unknowns.append(IRRIGATION_EQUIPMENT_UNKNOWN)

    if app.production_systems is not None:
        if scenario.production_system is None:
            unknowns.append(PRODUCTION_SYSTEM_UNKNOWN)
        elif scenario.production_system not in app.production_systems:
            reasons.append(_reason(PRODUCTION_SYSTEM_MISMATCH))
    else:
        unknowns.append(CATALOG_PRODUCTION_SCOPE_UNKNOWN)

    if app.crop_types is not None:
        if scenario.crop is None:
            unknowns.append(CROP_UNKNOWN)
        elif scenario.crop.strip().lower() not in {c.strip().lower() for c in app.crop_types}:
            reasons.append(_reason(CROP_NOT_APPLICABLE))
    else:
        unknowns.append(CATALOG_CROP_SCOPE_UNKNOWN)

    if app.soil_types is None:
        unknowns.append(CATALOG_SOIL_SCOPE_UNKNOWN)
    if app.climate_regimes is None:
        unknowns.append(CATALOG_CLIMATE_SCOPE_UNKNOWN)
    if app.farm_scales is None:
        unknowns.append(CATALOG_SCALE_SCOPE_UNKNOWN)

    if entry.benefit == "unknown":
        unknowns.append(BENEFIT_UNKNOWN)
    if entry.cost == "unknown":
        unknowns.append(COST_UNKNOWN)
    if entry.risk == "unknown":
        unknowns.append(RISK_UNKNOWN)

    return ConstraintResult(
        intervention_id=entry.intervention_id,
        eligible=not reasons,
        reasons=tuple(reasons),
        unknowns=tuple(unknowns),
    )


def evaluate_all(
    catalog: InterventionCatalog, scenario: ScenarioContext
) -> list[ConstraintResult]:
    """Evaluate every entry, keeping catalog order."""
    return [evaluate(entry, scenario) for entry in catalog.interventions]
