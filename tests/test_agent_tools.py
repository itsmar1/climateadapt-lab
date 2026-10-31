"""Offline tests for the agent tool wrappers. No network, no real credentials."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from climateadapt.agent import tools
from climateadapt.agent.tools import (
    BundleToolParams,
    RankingToolParams,
    RetrievalToolParams,
    get_environmental_bundle,
    rank_adaptation_options,
    retrieve_evidence,
    validate_report_tool,
)
from climateadapt.rag.models import RetrievedChunk
from climateadapt.schemas_era5 import EnvironmentalBundleResponse
from recommend_helpers import make_catalog, make_manifest
from report_helpers import make_llm_bundle, make_llm_chunks, make_llm_context, valid_report_dict


def bundle_params(**overrides) -> BundleToolParams:
    params = {
        "latitude": 30.43,
        "longitude": -9.61,
        "target_end_month": "2024-03",
        "timescale_months": 3,
        "reference_start_year": 1991,
        "reference_end_year": 2020,
        "min_reference_years": 30,
        "land_fallback_max_km": 15.0,
    }
    params.update(overrides)
    return BundleToolParams.model_validate(params)


def test_bundle_tool_maps_params_and_validates_response(monkeypatch):
    seen: dict = {}

    def fake_runner(chirps, era5, **kwargs):
        seen.update(kwargs)
        seen["chirps"] = chirps
        seen["era5"] = era5
        return make_llm_bundle()

    monkeypatch.setattr(tools, "run_environmental_bundle", fake_runner)
    response = get_environmental_bundle(bundle_params(), object(), object())

    assert isinstance(response, EnvironmentalBundleResponse)
    assert [e.indicator for e in response.entries] == [
        "chirps_spi", "era5_temperature_anomaly",
    ]
    assert seen["target_end_month"].year == 2024
    assert seen["target_end_month"].month == 3
    assert seen["timescale_months"] == 3
    assert seen["min_reference_years"] == 30
    assert seen["land_fallback_max_km"] == 15.0
    assert seen["latitude"] == 30.43


def test_bundle_tool_refuses_missing_clients():
    with pytest.raises(ValueError, match="both climate clients"):
        get_environmental_bundle(bundle_params(), None, object())


def test_retrieval_tool_uses_bm25_by_default():
    chunks = make_llm_chunks()
    result = retrieve_evidence(
        RetrievalToolParams.model_validate(
            {"query": "deficit irrigation scheduling", "top_k": 3}
        ),
        chunks,
    )

    assert result.retriever == "bm25"
    assert 1 <= len(result.hits) <= 3
    assert [hit.rank for hit in result.hits] == list(range(1, len(result.hits) + 1))
    known = {c.chunk_id for c in chunks}
    assert all(hit.chunk.chunk_id in known for hit in result.hits)


def test_retrieval_tool_uses_hybrid_when_dense_is_available():
    chunks = make_llm_chunks()

    class StubDense:
        name = "dense-test"

        def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(
                    chunk=chunk, score=0.9 - 0.1 * rank, rank=rank + 1,
                    component_ranks={"dense-test": rank + 1},
                    component_scores={"dense-test": 0.9 - 0.1 * rank},
                )
                for rank, chunk in enumerate(chunks[:2])
            ]

    result = retrieve_evidence(
        RetrievalToolParams.model_validate(
            {"query": "deficit irrigation", "top_k": 2, "exclude_reference": False}
        ),
        chunks,
        StubDense(),
    )

    assert result.retriever == "hybrid"
    assert len(result.hits) == 2


def test_ranking_tool_returns_the_deterministic_response():
    bundle = EnvironmentalBundleResponse.model_validate(make_llm_bundle())
    response = rank_adaptation_options(
        RankingToolParams.model_validate(
            {
                "crop": "wheat",
                "has_water_source": True,
                "has_irrigation_equipment": True,
                "production_system": "irrigated",
                "season": "2024-03",
                "latitude": 30.43,
                "longitude": -9.61,
            }
        ),
        bundle,
        make_catalog(),
        make_manifest(),
    )

    assert [o.intervention_id for o in response.ranked] == ["test-drip"]
    assert response.excluded == []
    assert len(response.limitations) >= 1


def test_validate_tool_accepts_and_rejects():
    ctx = make_llm_context()
    assert validate_report_tool(valid_report_dict(ctx), ctx).valid is True

    bad = valid_report_dict(ctx)
    bad["summary"]["text"] = "Severe drought everywhere."
    verdict = validate_report_tool(bad, ctx)
    assert verdict.valid is False
    assert any(p.startswith("[drought-label]") for p in verdict.problems)


def test_tool_param_models_reject_unknown_keys():
    with pytest.raises(ValidationError, match="Extra"):
        BundleToolParams.model_validate({**bundle_params().model_dump(), "x": 1})
    with pytest.raises(ValidationError, match="Extra"):
        RetrievalToolParams.model_validate({"query": "q", "x": 1})
    with pytest.raises(ValidationError, match="Extra"):
        RankingToolParams.model_validate({"crop": "wheat", "x": 1})
