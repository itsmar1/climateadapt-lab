"""Offline tests for the report schema and the tool-output registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from climateadapt.llm.report import (
    REPORT_SCHEMA_VERSION,
    Report,
    Statement,
    build_registry,
    dates_from_bundle,
)
from report_helpers import (
    make_llm_bundle,
    make_llm_context,
    make_llm_ranking,
    valid_report_dict,
)


def test_valid_draft_parses_and_round_trips():
    report = Report.model_validate(valid_report_dict())

    assert report.schema_version == REPORT_SCHEMA_VERSION
    assert report.generator == "fake:test-model"
    assert report.fallback is False
    assert len(report.environmental_findings) == 1
    assert len(report.provenance_refs) == 4
    assert Report.model_validate_json(report.model_dump_json()) == report


def test_statement_needs_evidence_or_tool_ids():
    with pytest.raises(ValidationError, match="evidence_ids and/or tool_output_ids"):
        Statement.model_validate({"text": "orphan claim"})


def test_statement_rejects_duplicate_ids():
    with pytest.raises(ValidationError, match="duplicates"):
        Statement.model_validate(
            {"text": "x", "evidence_ids": ["a:00001", "a:00001"]}
        )


def test_report_rejects_unknown_keys():
    draft = valid_report_dict()
    draft["summary"]["confidence"] = 0.99
    with pytest.raises(ValidationError):
        Report.model_validate(draft)


def test_report_requires_limitations_and_provenance():
    draft = valid_report_dict()
    draft["limitations"] = []
    with pytest.raises(ValidationError):
        Report.model_validate(draft)
    draft = valid_report_dict()
    draft["provenance_refs"] = []
    with pytest.raises(ValidationError):
        Report.model_validate(draft)


def test_registry_builders_collect_values_texts_labels_and_dates():
    registry = build_registry(make_llm_bundle(), make_llm_ranking())

    assert registry.lookup_number("bundle", "latitude") == 30.43
    assert registry.lookup_number("bundle", "reference_end_year") == 2020.0
    assert registry.lookup_number("chirps_spi", "spi") == -0.517
    assert registry.lookup_number("chirps_spi", "window_total_mm") == 76.87
    # Failed indicators register no values: nothing citable from a failed run.
    assert registry.outputs["era5_temperature_anomaly"].values == {}
    assert registry.has("era5_temperature_anomaly")
    ranking = registry.outputs["ranking:test-drip"]
    assert ranking.values["score_total"] == 0.85
    assert ranking.values["evidence_strength"] == 1.0
    assert ranking.texts == {"benefit": "unknown", "cost": "unknown", "risk": "unknown"}
    assert ranking.label == "Test drip"
    constraints = registry.outputs["constraints:test-flood"]
    assert constraints.texts == {"reason_codes": "no_water_source"}
    assert constraints.label == "Test flood"
    assert registry.outputs["chirps_spi"].texts == {"data_source": "CHIRPS v3.0"}
    assert registry.dates == {"2024-03", "2024-01"}
    assert dates_from_bundle(make_llm_bundle()) == {"2024-03", "2024-01"}


def test_registry_accepts_response_models_as_well_as_dicts():
    from climateadapt.recommend.schema import RecommendationResponse
    from climateadapt.schemas_era5 import EnvironmentalBundleResponse

    bundle = EnvironmentalBundleResponse.model_validate(make_llm_bundle())
    ranking = RecommendationResponse.model_validate(
        {**make_llm_ranking(), "scenario": {"crop": "wheat"}}
    )
    registry = build_registry(bundle, ranking)

    assert registry.lookup_number("chirps_spi", "spi") == -0.517
    assert registry.outputs["ranking:test-drip"].label == "Test drip"


def test_context_chunks_cover_the_valid_draft():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    used = set(draft["summary"]["evidence_ids"])
    used.update(draft["ranked_recommendations"][0]["narrative"]["evidence_ids"])

    assert used <= set(ctx.chunks)
    assert draft["evidence"][0]["chunk_id"] in ctx.chunks
