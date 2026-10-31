"""Recommendation entry point: constraints, then ranking, then the response."""

from __future__ import annotations

from climateadapt.rag.manifest import Manifest
from climateadapt.recommend.constraints import evaluate_all
from climateadapt.recommend.ranking import rank
from climateadapt.recommend.schema import (
    ExcludedOption,
    InterventionCatalog,
    RecommendationResponse,
    ScenarioContext,
)
from climateadapt.schemas_era5 import EnvironmentalBundleResponse

LIMITATIONS = (
    "Ranking reflects evidence traceability and indicator availability, "
    "not measured effectiveness.",
    "Benefit, cost and risk are unknown for every catalog entry unless a cited "
    "source states them; unknown is reported, never scored as zero.",
    "Indicator values are not interpreted as drought severity; relevance uses "
    "computation status only.",
    "This catalog version covers irrigation options only; other adaptation "
    "options are not ranked.",
)


def recommend(
    catalog: InterventionCatalog,
    scenario: ScenarioContext,
    bundle: EnvironmentalBundleResponse,
    manifest: Manifest,
    *,
    ingested_doc_ids: set[str] | None = None,
) -> RecommendationResponse:
    """Rank eligible interventions for one scenario plus bundle summary."""
    verdicts = evaluate_all(catalog, scenario)
    by_id = {entry.intervention_id: entry for entry in catalog.interventions}
    eligible = [
        (by_id[v.intervention_id], v) for v in verdicts if v.eligible
    ]
    ranked = rank(eligible, bundle, manifest, ingested_doc_ids=ingested_doc_ids)
    excluded = [
        ExcludedOption(
            intervention_id=v.intervention_id,
            name=by_id[v.intervention_id].name,
            category=by_id[v.intervention_id].category,
            evidence_status=by_id[v.intervention_id].evidence_status,
            reasons=list(v.reasons),
        )
        for v in verdicts
        if not v.eligible
    ]

    warnings: list[str] = []
    n_needs = sum(
        1 for entry in catalog.interventions if entry.evidence_status != "supported"
    )
    if n_needs:
        warnings.append(
            f"{n_needs} of {len(catalog.interventions)} catalog entries are marked "
            "needs_evidence and were excluded from ranking."
        )
    if not ranked:
        warnings.append("No eligible options: every catalog entry was excluded.")
    elif any(option.score_components["indicator_relevance"] < 1.0 for option in ranked):
        warnings.append(
            "Some relevant indicators were not computed (see score_inputs); "
            "relevance reflects availability only."
        )

    return RecommendationResponse(
        catalog_version=catalog.catalog_version,
        scenario=scenario,
        ranked=ranked,
        excluded=excluded,
        warnings=warnings,
        limitations=list(LIMITATIONS),
    )
