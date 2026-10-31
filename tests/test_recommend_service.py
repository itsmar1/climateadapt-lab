"""Service tests: end-to-end recommend() plus a real-catalog regression fixture."""

from __future__ import annotations

from pathlib import Path

from climateadapt.rag.manifest import load_manifest
from climateadapt.recommend.loader import load_catalog
from climateadapt.recommend.schema import ScenarioContext
from climateadapt.recommend.service import recommend
from recommend_helpers import make_bundle, make_catalog, make_entry, make_manifest, make_scenario

ROOT = Path(__file__).resolve().parents[1]


def _mixed_catalog():
    first = make_entry(intervention_id="a-first")
    second = make_entry(intervention_id="b-second")
    needs = make_entry(
        intervention_id="c-needs",
        evidence_status="needs_evidence",
        evidence_links=[],
        expected_sources=["test-doc-one"],
        needs_evidence_note="Supporting document is not ingested yet.",
    )
    return make_catalog(first, second, needs)


def test_recommend_splits_ranked_and_excluded():
    response = recommend(
        _mixed_catalog(), make_scenario(), make_bundle(), make_manifest("test-doc-one")
    )
    assert response.catalog_version == 1
    assert [o.intervention_id for o in response.ranked] == ["a-first", "b-second"]
    assert [o.intervention_id for o in response.excluded] == ["c-needs"]
    assert [r.code for r in response.excluded[0].reasons] == ["needs_evidence"]
    assert response.scenario == make_scenario()
    assert response.warnings == [
        "1 of 3 catalog entries are marked needs_evidence and were excluded from ranking."
    ]
    assert len(response.limitations) >= 1


def test_recommend_warns_when_nothing_is_eligible():
    catalog = make_catalog(
        make_entry(
            intervention_id="only-needs",
            evidence_status="needs_evidence",
            evidence_links=[],
            expected_sources=["test-doc-one"],
            needs_evidence_note="Supporting document is not ingested yet.",
        )
    )
    response = recommend(catalog, make_scenario(), make_bundle(), make_manifest("test-doc-one"))
    assert response.ranked == []
    assert len(response.excluded) == 1
    assert "No eligible options: every catalog entry was excluded." in response.warnings


def test_recommend_warns_when_relevant_indicators_are_missing():
    catalog = make_catalog(make_entry())
    bundle = make_bundle({"chirps_spi": "failed"})
    response = recommend(catalog, make_scenario(), bundle, make_manifest("test-doc-one"))
    (option,) = response.ranked
    assert option.score_components["indicator_relevance"] == 0.0
    assert option.score_inputs["indicator_statuses"] == {"chirps_spi": "failed"}
    assert any("availability only" in w for w in response.warnings)


def test_real_catalog_regression_fixture():
    """Pin the shipped catalog's output for one fixed scenario and bundle.

    Hand-checked: both supported entries are single-source (level 1 -> 0.5),
    all relevant indicators are ok (relevance 1.0), fit is 1.0, so each total
    is 0.5*0.5 + 0.3*1.0 + 0.2*1.0 = 0.75 and the tie breaks by id.
    """
    catalog = load_catalog()
    manifest = load_manifest(ROOT / "corpus" / "manifest.json")
    scenario = ScenarioContext.model_validate(
        {
            "crop": "wheat",
            "has_water_source": True,
            "has_irrigation_equipment": True,
            "production_system": "irrigated",
        }
    )
    response = recommend(catalog, scenario, make_bundle(), manifest)

    assert response.catalog_version == 1
    assert [o.intervention_id for o in response.ranked] == [
        "deficit-irrigation",
        "irrigation-scheduling",
    ]
    for option in response.ranked:
        assert option.score_components == {
            "evidence_strength": 0.5,
            "indicator_relevance": 1.0,
            "constraint_fit": 1.0,
        }
        assert option.score_total == 0.75
        assert option.score_inputs["evidence_level"] == 1
        assert option.unknowns == [
            "catalog_crop_scope_unknown",
            "catalog_soil_scope_unknown",
            "catalog_climate_scope_unknown",
            "catalog_scale_scope_unknown",
            "benefit_unknown",
            "cost_unknown",
            "risk_unknown",
        ]
        assert len(option.evidence) == 2
        assert {ref.doc_id for ref in option.evidence} == {
            "fao-iddp66-crop-yield-response-to-water"
        }
    assert [o.pdf_page for o in response.ranked[0].evidence] == [22, 70]
    assert [o.pdf_page for o in response.ranked[1].evidence] == [25, 66]
    assert "Steduto et al. (2012)" in response.ranked[0].evidence[0].citation

    (excluded,) = response.excluded
    assert excluded.intervention_id == "supplemental-irrigation"
    assert [r.code for r in excluded.reasons] == ["needs_evidence", "production_system_mismatch"]
    assert response.warnings == [
        "1 of 3 catalog entries are marked needs_evidence and were excluded from ranking."
    ]
