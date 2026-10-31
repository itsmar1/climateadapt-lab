"""Schema tests: catalog validation, explicit unknowns, evidence consistency."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from climateadapt.recommend.loader import load_catalog
from climateadapt.recommend.schema import (
    CATALOG_VERSION,
    Intervention,
    InterventionCatalog,
    ScenarioContext,
)
from recommend_helpers import make_catalog, make_entry, make_scenario

ROOT = Path(__file__).resolve().parents[1]


def test_packaged_catalog_loads_with_expected_shape():
    catalog = load_catalog()
    assert catalog.catalog_version == CATALOG_VERSION == 1
    assert [e.intervention_id for e in catalog.interventions] == [
        "deficit-irrigation",
        "irrigation-scheduling",
        "supplemental-irrigation",
    ]


def test_packaged_catalog_states_no_benefit_cost_or_risk():
    for entry in load_catalog().interventions:
        assert entry.benefit == "unknown"
        assert entry.cost == "unknown"
        assert entry.risk == "unknown"
        assert entry.benefit_evidence == entry.cost_evidence == entry.risk_evidence == []


def test_packaged_catalog_evidence_status_is_consistent():
    by_id = {e.intervention_id: e for e in load_catalog().interventions}
    for supported in ("deficit-irrigation", "irrigation-scheduling"):
        assert by_id[supported].evidence_status == "supported"
        assert len(by_id[supported].evidence_links) == 2
        assert by_id[supported].needs_evidence_note is None
    needs = by_id["supplemental-irrigation"]
    assert needs.evidence_status == "needs_evidence"
    assert needs.evidence_links == []
    assert len(needs.expected_sources) == 2
    assert needs.needs_evidence_note is not None


def test_valid_entry_parses():
    assert make_entry().intervention_id == "test-drip"


def _entry_overrides(**overrides):
    base = make_entry().model_dump()
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"evidence_links": []}, "at least one evidence link"),
        ({"evidence_status": "needs_evidence", "evidence_links": []}, "needs_evidence_note"),
        (
            {
                "evidence_status": "needs_evidence",
                "needs_evidence_note": "Not ingested yet, wait.",
            },
            "must not carry evidence links",
        ),
        ({"needs_evidence_note": "stray note"}, "must be null"),
        ({"expected_sources": ["test-doc-one"]}, "expected_sources must be empty"),
        (
            {"evidence_links": [
                {"doc_id": "ddd", "pdf_page": 1, "reference": "locator one"},
                {"doc_id": "ddd", "pdf_page": 1, "reference": "locator two"},
            ]},
            "duplicate",
        ),
        ({"benefit": "Raises yield"}, "without evidence"),
        ({"benefit": "Unknown"}, "without evidence"),
        ({"benefit_evidence": [0]}, "not empty"),
        ({"benefit": "Raises yield", "benefit_evidence": [5]}, "out of range"),
        ({"benefit": "Raises yield", "benefit_evidence": [0, 0]}, "duplicate indices"),
        ({"cost": "Cheap", "cost_evidence": []}, "without evidence"),
        ({"risk": "None", "risk_evidence": []}, "without evidence"),
        ({"relevant_indicators": ["chirps_spi", "chirps_spi"]}, "duplicates"),
        ({"relevant_indicators": ["ndvi"]}, "not in the bundle schema"),
        ({"relevant_indicators": []}, "too_short"),
        ({"intervention_id": "Bad_ID"}, "pattern"),
        ({"unexpected": 1}, "unexpected"),
    ],
)
def test_invalid_entries_are_rejected(overrides, match):
    with pytest.raises(ValidationError, match=match):
        Intervention.model_validate(_entry_overrides(**overrides))


def test_stated_benefit_with_evidence_parses():
    entry = make_entry(benefit="Raises yield in trials", benefit_evidence=[0])
    assert entry.benefit_evidence == [0]


def test_wrong_catalog_version_is_rejected():
    data = make_catalog().model_dump()
    data["catalog_version"] = 99
    with pytest.raises(ValidationError, match="not supported"):
        InterventionCatalog.model_validate(data)


def test_duplicate_intervention_ids_are_rejected():
    data = make_catalog().model_dump()
    data["interventions"] = [data["interventions"][0], data["interventions"][0]]
    with pytest.raises(ValidationError, match="duplicate intervention_id"):
        InterventionCatalog.model_validate(data)


def test_empty_catalog_is_rejected():
    with pytest.raises(ValidationError):
        InterventionCatalog.model_validate(
            {"catalog_version": 1, "description": "Empty test catalog.", "interventions": []}
        )


def test_scenario_accepts_full_unknowns():
    scenario = ScenarioContext.model_validate({})
    assert scenario.crop is None
    assert scenario.has_water_source is None
    assert scenario.latitude is None


def test_scenario_matches_default_entry():
    scenario = make_scenario()
    assert scenario.crop == "wheat"
    assert scenario.production_system == "irrigated"


@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": "30.43"},
        {"latitude": float("nan")},
        {"longitude": float("inf")},
        {"latitude": 91.0},
        {"has_water_source": 1},
        {"crop": ""},
        {"unexpected": 1},
    ],
)
def test_invalid_scenarios_are_rejected(overrides):
    data = make_scenario().model_dump()
    data.update(overrides)
    with pytest.raises(ValidationError):
        ScenarioContext.model_validate(data)
