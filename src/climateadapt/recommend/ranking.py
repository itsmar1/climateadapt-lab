"""Transparent ranking: documented components, exposed inputs, deterministic ties.

Total = EVIDENCE_WEIGHT * evidence_strength
     + INDICATOR_WEIGHT * indicator_relevance
     + CONSTRAINT_FIT_WEIGHT * constraint_fit

* ``evidence_strength``: rubric level / 2 (see ``evidence.py``).
* ``indicator_relevance``: fraction of the entry's relevant bundle indicators
  whose status is ``ok``. Availability only — indicator *values* are never
  interpreted, so no drought-severity reading sneaks in through the score.
* ``constraint_fit``: 1.0 for every ranked option by construction (excluded
  options are not ranked; the gate itself is in ``constraints.py``). It is kept
  as an explicit component so the breakdown shows the gate passed.

Ties break by ``intervention_id`` ascending. Unknowns are listed on each
option and never enter the arithmetic.
"""

from __future__ import annotations

from climateadapt.rag.manifest import Manifest
from climateadapt.recommend.constraints import ConstraintResult
from climateadapt.recommend.evidence import (
    evidence_level,
    evidence_score,
    format_evidence_reference,
    resolvable_links,
)
from climateadapt.recommend.schema import (
    Intervention,
    RankedOption,
)
from climateadapt.schemas_era5 import EnvironmentalBundleResponse

EVIDENCE_WEIGHT = 0.5
INDICATOR_WEIGHT = 0.3
CONSTRAINT_FIT_WEIGHT = 0.2

SCORE_WEIGHTS = {
    "evidence_strength": EVIDENCE_WEIGHT,
    "indicator_relevance": INDICATOR_WEIGHT,
    "constraint_fit": CONSTRAINT_FIT_WEIGHT,
}


def indicator_relevance(
    entry: Intervention, bundle: EnvironmentalBundleResponse
) -> tuple[float, dict[str, str]]:
    """Fraction of relevant indicators with status ``ok``, plus per-indicator inputs."""
    statuses = {item.indicator: item.status for item in bundle.entries}
    per_indicator: dict[str, str] = {}
    n_ok = 0
    for name in entry.relevant_indicators:
        status = statuses.get(name, "missing")
        per_indicator[name] = status
        if status == "ok":
            n_ok += 1
    return n_ok / len(entry.relevant_indicators), per_indicator


def rank(
    eligible: list[tuple[Intervention, ConstraintResult]],
    bundle: EnvironmentalBundleResponse,
    manifest: Manifest,
    *,
    ingested_doc_ids: set[str] | None = None,
) -> list[RankedOption]:
    """Score eligible options. Raises KeyError when evidence misses the manifest."""
    ranked: list[RankedOption] = []
    for entry, verdict in eligible:
        level = evidence_level(entry, ingested_doc_ids)
        components = {
            "evidence_strength": evidence_score(entry, ingested_doc_ids),
            "indicator_relevance": 0.0,
            "constraint_fit": 1.0,
        }
        relevance, per_indicator = indicator_relevance(entry, bundle)
        components["indicator_relevance"] = relevance
        total = sum(SCORE_WEIGHTS[name] * value for name, value in components.items())
        ranked.append(
            RankedOption(
                intervention_id=entry.intervention_id,
                name=entry.name,
                category=entry.category,
                score_total=total,
                score_components=dict(components),
                score_weights=dict(SCORE_WEIGHTS),
                score_inputs={
                    "evidence_level": level,
                    "evidence_doc_ids": sorted(
                        {link.doc_id for link in resolvable_links(entry, ingested_doc_ids)}
                    ),
                    "indicator_statuses": per_indicator,
                    "exclusion_reasons": 0,
                },
                unknowns=list(verdict.unknowns),
                evidence=[
                    format_evidence_reference(link, manifest)
                    for link in resolvable_links(entry, ingested_doc_ids)
                ],
                benefit=entry.benefit,
                cost=entry.cost,
                risk=entry.risk,
            )
        )
    ranked.sort(key=lambda option: (-option.score_total, option.intervention_id))
    return ranked
