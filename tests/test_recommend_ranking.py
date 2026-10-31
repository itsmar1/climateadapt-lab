"""Ranking tests: rubric, relevance, breakdowns, determinism, unknown handling."""

from __future__ import annotations

import pytest

from climateadapt.recommend.constraints import evaluate
from climateadapt.recommend.evidence import (
    MAX_EVIDENCE_LEVEL,
    evidence_level,
    evidence_score,
    format_evidence_reference,
)
from climateadapt.recommend.ranking import SCORE_WEIGHTS, indicator_relevance, rank
from recommend_helpers import make_bundle, make_entry, make_manifest, make_scenario


def test_rubric_needs_evidence_is_level_zero():
    entry = make_entry(
        evidence_status="needs_evidence",
        evidence_links=[],
        expected_sources=["test-doc-one"],
        needs_evidence_note="Supporting document is not ingested yet.",
    )
    assert evidence_level(entry) == 0
    assert evidence_score(entry) == 0.0


def test_rubric_single_document_is_level_one():
    assert evidence_level(make_entry()) == 1
    assert evidence_score(make_entry()) == 0.5


def test_rubric_two_documents_is_level_two():
    entry = make_entry(
        evidence_links=[
            {"doc_id": "doc-a", "pdf_page": 1, "reference": "Locator A"},
            {"doc_id": "doc-b", "pdf_page": 2, "reference": "Locator B"},
        ]
    )
    assert evidence_level(entry) == 2
    assert evidence_score(entry) == 1.0


def test_rubric_ignores_links_to_non_ingested_documents():
    entry = make_entry(
        evidence_links=[
            {"doc_id": "doc-a", "pdf_page": 1, "reference": "Locator A"},
            {"doc_id": "doc-b", "pdf_page": 2, "reference": "Locator B"},
        ]
    )
    assert evidence_level(entry, {"doc-a"}) == 1
    assert evidence_level(entry, {"doc-a", "doc-b"}) == 2
    assert evidence_level(entry, set()) == 0


def test_rubric_max_level_is_two():
    assert MAX_EVIDENCE_LEVEL == 2


def test_score_weights_sum_to_one():
    assert set(SCORE_WEIGHTS) == {"evidence_strength", "indicator_relevance", "constraint_fit"}
    assert SCORE_WEIGHTS["evidence_strength"] == 0.5
    assert SCORE_WEIGHTS["indicator_relevance"] == 0.3
    assert SCORE_WEIGHTS["constraint_fit"] == 0.2
    assert sum(SCORE_WEIGHTS.values()) == pytest.approx(1.0)


def test_relevance_counts_ok_statuses_only():
    entry = make_entry(relevant_indicators=["chirps_spi", "era5_spi"])
    bundle = make_bundle({"chirps_spi": "ok", "era5_spi": "failed"})
    score, per_indicator = indicator_relevance(entry, bundle)
    assert score == 0.5
    assert per_indicator == {"chirps_spi": "ok", "era5_spi": "failed"}


def test_relevance_reports_missing_indicators_as_missing():
    entry = make_entry(relevant_indicators=["chirps_spi"])
    bundle = make_bundle()
    bundle.entries = [e for e in bundle.entries if e.indicator != "chirps_spi"]
    score, per_indicator = indicator_relevance(entry, bundle)
    assert score == 0.0
    assert per_indicator == {"chirps_spi": "missing"}


def _ranked_single(**entry_overrides):
    entry = make_entry(**entry_overrides)
    scenario = make_scenario()
    (option,) = rank(
        [(entry, evaluate(entry, scenario))], make_bundle(), make_manifest("test-doc-one")
    )
    return option


def test_ranked_option_exposes_a_complete_breakdown():
    option = _ranked_single()
    assert option.score_components == {
        "evidence_strength": 0.5,
        "indicator_relevance": 1.0,
        "constraint_fit": 1.0,
    }
    assert option.score_weights == SCORE_WEIGHTS
    assert option.score_total == pytest.approx(0.5 * 0.5 + 0.3 * 1.0 + 0.2 * 1.0)
    assert option.score_inputs == {
        "evidence_level": 1,
        "evidence_doc_ids": ["test-doc-one"],
        "indicator_statuses": {"chirps_spi": "ok"},
        "exclusion_reasons": 0,
    }
    assert option.unknowns == ["benefit_unknown", "cost_unknown", "risk_unknown"]
    assert option.benefit == option.cost == option.risk == "unknown"


def test_ranked_evidence_comes_from_the_manifest():
    option = _ranked_single()
    (ref,) = option.evidence
    assert ref.doc_id == "test-doc-one"
    assert ref.pdf_page == 3
    assert ref.reference == "Test locator"
    assert ref.citation == (
        "Author (2020). A test document. Test Publisher. p. 3 (PDF index; no printed label)."
    )
    assert ref.landing_url == "https://example.org/doc"
    assert ref.license_status == "verified_in_record"


def test_ranking_missing_manifest_document_is_an_error():
    entry = make_entry()
    with pytest.raises(KeyError):
        rank([(entry, evaluate(entry, make_scenario()))], make_bundle(), make_manifest("other"))


def test_ranking_is_deterministic_and_breaks_ties_by_id():
    low = make_entry(intervention_id="a-low")
    high = make_entry(intervention_id="z-high")
    scenario = make_scenario()
    manifest = make_manifest("test-doc-one")
    first = rank(
        [(high, evaluate(high, scenario)), (low, evaluate(low, scenario))],
        make_bundle(), manifest,
    )
    second = rank(
        [(high, evaluate(high, scenario)), (low, evaluate(low, scenario))],
        make_bundle(), manifest,
    )
    assert [o.intervention_id for o in first] == ["a-low", "z-high"]
    assert first[0].score_total == first[1].score_total
    assert [o.model_dump() for o in first] == [o.model_dump() for o in second]


def test_unknowns_do_not_change_the_score():
    entry = make_entry()
    manifest = make_manifest("test-doc-one")
    bundle = make_bundle()
    known = rank([(entry, evaluate(entry, make_scenario()))], bundle, manifest)[0]
    vague = make_scenario(
        crop=None, has_water_source=None, has_irrigation_equipment=None,
        production_system=None,
    )
    unknown = rank([(entry, evaluate(entry, vague))], bundle, manifest)[0]
    assert unknown.score_total == known.score_total
    assert unknown.score_components["constraint_fit"] == 1.0
    assert len(unknown.unknowns) > len(known.unknowns)


def test_format_reference_handles_missing_year_and_series():
    manifest = make_manifest("test-doc-one")
    doc = manifest.doc_ids[0]
    assert doc == "test-doc-one"
    link = make_entry().evidence_links[0]
    ref = format_evidence_reference(link, manifest)
    assert "(2020)" in ref.citation
