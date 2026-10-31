"""Constraint tests: each hard rule, reason codes, and unknown handling."""

from __future__ import annotations

from climateadapt.recommend.constraints import (
    CROP_NOT_APPLICABLE,
    NEEDS_EVIDENCE,
    NO_IRRIGATION_EQUIPMENT,
    NO_WATER_SOURCE,
    PRODUCTION_SYSTEM_MISMATCH,
    evaluate,
    evaluate_all,
)
from recommend_helpers import make_catalog, make_entry, make_scenario


def codes(result) -> list[str]:
    return [reason.code for reason in result.reasons]


def test_matching_scenario_is_eligible_with_only_value_unknowns():
    result = evaluate(make_entry(), make_scenario())
    assert result.eligible
    assert result.reasons == ()
    assert result.unknowns == ("benefit_unknown", "cost_unknown", "risk_unknown")


def test_needs_evidence_is_excluded():
    entry = make_entry(
        evidence_status="needs_evidence",
        evidence_links=[],
        expected_sources=["test-doc-one"],
        needs_evidence_note="Supporting document is not ingested yet.",
    )
    result = evaluate(entry, make_scenario())
    assert not result.eligible
    assert codes(result) == [NEEDS_EVIDENCE]


def test_no_water_source_is_excluded():
    result = evaluate(make_entry(), make_scenario(has_water_source=False))
    assert not result.eligible
    assert codes(result) == [NO_WATER_SOURCE]


def test_unknown_water_source_stays_eligible_and_is_recorded():
    result = evaluate(make_entry(), make_scenario(has_water_source=None))
    assert result.eligible
    assert "water_source_unknown" in result.unknowns


def test_unknown_catalog_water_requirement_is_recorded():
    app = {**make_entry().applicability.model_dump(), "requires_water_source": None}
    entry = make_entry(applicability=app)
    result = evaluate(entry, make_scenario(has_water_source=False))
    assert result.eligible
    assert "catalog_water_requirement_unknown" in result.unknowns


def test_no_irrigation_equipment_is_excluded_for_irrigation():
    result = evaluate(make_entry(), make_scenario(has_irrigation_equipment=False))
    assert not result.eligible
    assert codes(result) == [NO_IRRIGATION_EQUIPMENT]


def test_unknown_equipment_stays_eligible_and_is_recorded():
    result = evaluate(make_entry(), make_scenario(has_irrigation_equipment=None))
    assert result.eligible
    assert "irrigation_equipment_unknown" in result.unknowns


def test_equipment_is_ignored_for_non_irrigation_entries():
    entry = make_entry(category="planning")
    result = evaluate(entry, make_scenario(has_irrigation_equipment=False))
    assert result.eligible
    assert "irrigation_equipment_unknown" not in result.unknowns


def test_production_system_mismatch_is_excluded():
    result = evaluate(make_entry(), make_scenario(production_system="rainfed"))
    assert not result.eligible
    assert codes(result) == [PRODUCTION_SYSTEM_MISMATCH]


def test_unknown_production_system_stays_eligible_and_is_recorded():
    result = evaluate(make_entry(), make_scenario(production_system=None))
    assert result.eligible
    assert "production_system_unknown" in result.unknowns


def test_crop_mismatch_is_excluded():
    result = evaluate(make_entry(), make_scenario(crop="maize"))
    assert not result.eligible
    assert codes(result) == [CROP_NOT_APPLICABLE]


def test_crop_match_is_case_insensitive():
    assert evaluate(make_entry(), make_scenario(crop="Wheat")).eligible


def test_unknown_crop_stays_eligible_and_is_recorded():
    result = evaluate(make_entry(), make_scenario(crop=None))
    assert result.eligible
    assert "crop_unknown" in result.unknowns


def test_unknown_catalog_crop_scope_is_recorded():
    app = {**make_entry().applicability.model_dump(), "crop_types": None}
    entry = make_entry(applicability=app)
    result = evaluate(entry, make_scenario(crop="maize"))
    assert result.eligible
    assert "catalog_crop_scope_unknown" in result.unknowns


def test_all_reasons_are_collected_in_fixed_order():
    entry = make_entry(
        evidence_status="needs_evidence",
        evidence_links=[],
        expected_sources=["test-doc-one"],
        needs_evidence_note="Supporting document is not ingested yet.",
    )
    result = evaluate(
        entry,
        make_scenario(
            has_water_source=False, has_irrigation_equipment=False,
            production_system="rainfed", crop="maize",
        ),
    )
    assert codes(result) == [
        NEEDS_EVIDENCE,
        NO_WATER_SOURCE,
        NO_IRRIGATION_EQUIPMENT,
        PRODUCTION_SYSTEM_MISMATCH,
        CROP_NOT_APPLICABLE,
    ]


def test_fully_unknown_scenario_never_excludes_supported():
    app = {**make_entry().applicability.model_dump(), "crop_types": None}
    entry = make_entry(applicability=app)
    scenario = make_scenario(
        crop=None, has_water_source=None, has_irrigation_equipment=None,
        production_system=None,
    )
    result = evaluate(entry, scenario)
    assert result.eligible
    assert "water_source_unknown" in result.unknowns
    assert "catalog_crop_scope_unknown" in result.unknowns


def test_evaluate_all_keeps_catalog_order():
    first = make_entry(intervention_id="a-first")
    second = make_entry(intervention_id="b-second")
    results = evaluate_all(make_catalog(first, second), make_scenario())
    assert [r.intervention_id for r in results] == ["a-first", "b-second"]
    assert all(r.eligible for r in results)
