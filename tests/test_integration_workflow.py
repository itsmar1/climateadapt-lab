"""Integration across the complete workflow: store -> agent -> detail.

Only the network boundaries are faked (bundle fetch stubbed, FakeProvider or
the unavailable stand-in for the draft). Retrieval (real BM25), ranking (real
service over a synthetic catalog), validation, fallback, persistence, and
detail assembly all run for real. No network, no credentials, no TestClient
(runs in restricted sandboxes too).
"""

from __future__ import annotations

import json

from climateadapt.agent import workflow
from climateadapt.agent.schemas import AgentConfig, AgentDeps, AgentScenario
from climateadapt.agent.tools import (
    RankingToolParams,
    RetrievalToolParams,
    rank_adaptation_options,
    retrieve_evidence,
)
from climateadapt.api.dependencies import UnavailableProvider
from climateadapt.api.scenarios import run_scenario_job, to_detail
from climateadapt.api.store import SqliteScenarioStore
from climateadapt.llm.provider import FakeProvider, LLMUsage
from climateadapt.rag.models import RetrievedChunk
from climateadapt.schemas_era5 import EnvironmentalBundleResponse
from recommend_helpers import make_catalog, make_entry
from report_helpers import (
    evidence_entry,
    make_llm_bundle,
    make_llm_chunks,
    make_llm_manifest,
    make_llm_pages,
)


def make_scenario() -> AgentScenario:
    return AgentScenario.model_validate(
        {
            "latitude": 30.43,
            "longitude": -9.61,
            "target_end_month": "2024-03",
            "timescale_months": 3,
            "reference_start_year": 1991,
            "reference_end_year": 2020,
            "min_reference_years": 30,
            "land_fallback_max_km": 15.0,
            "query": "deficit irrigation scheduling",
            "top_k": 5,
            "exclude_reference": True,
            "crop": "wheat",
            "has_water_source": True,
            "has_irrigation_equipment": True,
            "production_system": "irrigated",
            "season": "2024-03",
        }
    )


def make_deps() -> AgentDeps:
    """Real offline deps; clients stay None (bundle tool is stubbed)."""
    return AgentDeps(
        chirps=None,
        era5=None,
        chunks=make_llm_chunks(),
        manifest=make_llm_manifest(),
        pages_by_doc=make_llm_pages(),
        catalog=make_catalog(
            make_entry(),
            make_entry(
                intervention_id="test-flood",
                name="Test flood",
                evidence_status="needs_evidence",
                evidence_links=[],
                needs_evidence_note="Synthetic note: no ingested source covers this yet.",
                expected_sources=["test-doc-two"],
            ),
        ),
    )


def stub_bundle(monkeypatch) -> EnvironmentalBundleResponse:
    response = EnvironmentalBundleResponse.model_validate(make_llm_bundle())
    monkeypatch.setattr(workflow, "get_environmental_bundle", lambda *a, **k: response)
    return response


def run_job(store, scenario_id, deps, provider, config=None):
    job = run_scenario_job(
        scenario_id, store=store, deps=deps, provider=provider, config=config
    )
    return job(lambda done, total: None)


def integration_draft(*, retrieved_ids, ranking) -> dict:
    """A draft built from the REAL ranking values (exact floats, f-string text)."""
    ranked = ranking["ranked"]
    excluded = ranking["excluded"]
    first_id = retrieved_ids[0]
    recs = []
    for option in ranked:
        score = option["score_total"]
        recs.append(
            {
                "intervention_id": option["intervention_id"],
                "name": option["name"],
                "benefit": option["benefit"],
                "cost": option["cost"],
                "risk": option["risk"],
                "narrative": {
                    "text": (
                        f"{option['name']} ({option['intervention_id']}): "
                        f"ranked with score {score}."
                    ),
                    "evidence_ids": [first_id],
                    "tool_output_ids": [f"ranking:{option['intervention_id']}"],
                    "numbers": [
                        {
                            "value": score,
                            "unit": None,
                            "tool_output_id": f"ranking:{option['intervention_id']}",
                            "field": "score_total",
                        }
                    ],
                },
            }
        )
    excluded_opts = []
    for option in excluded:
        codes = [reason["code"] for reason in option["reasons"]]
        excluded_opts.append(
            {
                "intervention_id": option["intervention_id"],
                "name": option["name"],
                "reason_codes": codes,
                "narrative": {
                    "text": (
                        f"{option['name']} ({option['intervention_id']}): excluded. "
                        f"Reasons: {', '.join(codes)}."
                    ),
                    "evidence_ids": [],
                    "tool_output_ids": [f"constraints:{option['intervention_id']}"],
                    "numbers": [],
                },
            }
        )
    refs = ["bundle", "chirps_spi"]
    refs.extend(f"ranking:{o['intervention_id']}" for o in ranked)
    refs.extend(f"constraints:{o['intervention_id']}" for o in excluded)
    return {
        "schema_version": 1,
        "generator": "fake:integration-model",
        "fallback": False,
        "fallback_note": None,
        "summary": {
            "text": "Analysis for the requested location and window is complete.",
            "evidence_ids": [first_id],
            "tool_output_ids": ["bundle"],
            "numbers": [],
        },
        "environmental_findings": [
            {
                "text": (
                    "CHIRPS SPI is -0.517 for a window total of 76.87 mm, "
                    "using 30 reference years."
                ),
                "evidence_ids": [],
                "tool_output_ids": ["chirps_spi"],
                "numbers": [
                    {"value": -0.517, "unit": None,
                     "tool_output_id": "chirps_spi", "field": "spi"},
                    {"value": 76.87, "unit": "mm",
                     "tool_output_id": "chirps_spi", "field": "window_total_mm"},
                    {"value": 30.0, "unit": None,
                     "tool_output_id": "chirps_spi", "field": "reference_years_used"},
                ],
            }
        ],
        "evidence": [],  # filled by the caller with rebuilt entries
        "ranked_recommendations": recs,
        "excluded_options": excluded_opts,
        "limitations": [
            "Indicator values are reported without drought categories or composite scores.",
            "Benefit, cost and risk are unknown unless the catalog cites a source.",
        ],
        "assumptions": ["Retrieved passages are cited for traceability."],
        "data_coverage": {
            "text": (
                "Location 30.43, -9.61; target window ending 2024-03; "
                "timescale 3 months; reference 1991 to 2020."
            ),
            "evidence_ids": [],
            "tool_output_ids": ["bundle"],
            "numbers": [
                {"value": 30.43, "unit": "deg",
                 "tool_output_id": "bundle", "field": "latitude"},
                {"value": -9.61, "unit": "deg",
                 "tool_output_id": "bundle", "field": "longitude"},
                {"value": 3.0, "unit": "months",
                 "tool_output_id": "bundle", "field": "timescale_months"},
                {"value": 1991.0, "unit": None,
                 "tool_output_id": "bundle", "field": "reference_start_year"},
                {"value": 2020.0, "unit": None,
                 "tool_output_id": "bundle", "field": "reference_end_year"},
            ],
        },
        "provenance_refs": refs,
    }


def real_ranking(*, deps, bundle, hits: list[RetrievedChunk]):
    """The REAL ranking tool over the stubbed bundle (mirrors the workflow)."""
    scenario = make_scenario()
    return rank_adaptation_options(
        RankingToolParams(
            crop=scenario.crop,
            has_water_source=scenario.has_water_source,
            has_irrigation_equipment=scenario.has_irrigation_equipment,
            production_system=scenario.production_system,
            season=scenario.season,
            latitude=scenario.latitude,
            longitude=scenario.longitude,
        ),
        bundle,
        deps.catalog,
        deps.manifest,
        ingested_doc_ids={hit.chunk.doc_id for hit in hits},
    )


def draft_provider_for(*, deps, bundle) -> FakeProvider:
    """FakeProvider whose draft cites REAL retrieval hits and ranking values."""
    scenario = make_scenario()
    found = retrieve_evidence(
        RetrievalToolParams(
            query=scenario.query, top_k=scenario.top_k,
            exclude_reference=scenario.exclude_reference,
        ),
        deps.chunks,
    )
    assert found.hits, "synthetic corpus must match the scenario query"
    ranking = real_ranking(deps=deps, bundle=bundle, hits=found.hits)
    retrieved_ids = [hit.chunk.chunk_id for hit in found.hits]
    by_id = {chunk.chunk_id: chunk for chunk in deps.chunks}
    draft = integration_draft(
        retrieved_ids=retrieved_ids, ranking=ranking.model_dump(mode="json")
    )
    # The draft cites the first hit; it must sit inside the evidence list.
    draft["evidence"] = [evidence_entry(by_id[retrieved_ids[0]], deps.manifest)]
    usage = LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    return FakeProvider.with_text(json.dumps(draft), usage=usage)


def stored_detail(store, scenario_id) -> dict:
    row = store.get(scenario_id)
    assert row is not None
    detail = to_detail(row)
    dumped = detail.model_dump(mode="json")
    json.dumps(dumped)  # the API must serve JSON-serializable rows
    return dumped


def test_full_run_persists_complete_detail(tmp_path, monkeypatch):
    """Happy path: real BM25 + real ranking + accepted draft -> complete row."""
    deps = make_deps()
    bundle = stub_bundle(monkeypatch)
    store = SqliteScenarioStore(tmp_path / "scenarios.sqlite3")
    scenario = make_scenario()
    store.create("sc-int-1", "job-int-1", scenario.model_dump(mode="json"))

    provider = draft_provider_for(deps=deps, bundle=bundle)
    outcome = run_job(store, "sc-int-1", deps, provider, AgentConfig())
    assert outcome == {"scenario_id": "sc-int-1", "status": "complete"}

    dumped = stored_detail(store, "sc-int-1")
    assert dumped["status"] == "complete"
    assert dumped["version"] == 1
    assert dumped["bundle"]["entries"][0]["indicator"] == "chirps_spi"
    assert dumped["ranking"]["ranked"][0]["intervention_id"] == "test-drip"
    assert dumped["ranking"]["excluded"][0]["intervention_id"] == "test-flood"
    assert dumped["report"]["generator"] == "fake:integration-model"
    assert dumped["report"]["fallback"] is False
    assert dumped["problems"] == []
    stages = {stage["name"]: stage["status"] for stage in dumped["trace"]["stages"]}
    assert stages == {
        "validate_inputs": "ok",
        "bundle": "ok",
        "retrieval": "ok",
        "ranking": "ok",
        "draft": "ok",
        "validate": "ok",
        "finalize": "ok",
    }
    assert dumped["trace"]["tool_calls"], "trace must record tool calls"
    store.close()


def test_unavailable_provider_yields_labelled_fallback(tmp_path, monkeypatch):
    """No-key run: deterministic outputs persist with the fallback report."""
    deps = make_deps()
    stub_bundle(monkeypatch)
    store = SqliteScenarioStore(tmp_path / "scenarios.sqlite3")
    scenario = make_scenario()
    store.create("sc-int-2", "job-int-2", scenario.model_dump(mode="json"))

    outcome = run_job(store, "sc-int-2", deps, UnavailableProvider(), AgentConfig())
    assert outcome == {"scenario_id": "sc-int-2", "status": "partial"}

    dumped = stored_detail(store, "sc-int-2")
    assert dumped["bundle"] is not None
    assert dumped["ranking"] is not None
    assert dumped["report"]["fallback"] is True
    assert dumped["report"]["generator"] == "deterministic-fallback"
    assert any(problem.startswith("[provider-auth]") for problem in dumped["problems"])
    assert dumped["report"]["limitations"], "fallback keeps mandatory limitations"
    store.close()


def test_rejected_draft_yields_fallback_with_validator_problems(tmp_path, monkeypatch):
    """A draft citing an unknown chunk is rejected; the fallback is served."""
    deps = make_deps()
    stub_bundle(monkeypatch)
    store = SqliteScenarioStore(tmp_path / "scenarios.sqlite3")
    scenario = make_scenario()
    store.create("sc-int-3", "job-int-3", scenario.model_dump(mode="json"))

    bad = integration_draft(retrieved_ids=["ghost-chunk:1"], ranking={
        "ranked": [], "excluded": [],
    })
    bad["summary"]["evidence_ids"] = ["ghost-chunk:1"]
    provider = FakeProvider.with_text(
        json.dumps(bad),
        usage=LLMUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )
    outcome = run_job(store, "sc-int-3", deps, provider, AgentConfig())
    assert outcome == {"scenario_id": "sc-int-3", "status": "partial"}

    dumped = stored_detail(store, "sc-int-3")
    assert dumped["report"]["fallback"] is True
    assert any("unknown" in problem for problem in dumped["problems"])
    store.close()


def test_detail_survives_store_reopen(tmp_path, monkeypatch):
    """Persistence across restarts: close and reopen the same database file."""
    deps = make_deps()
    stub_bundle(monkeypatch)
    path = tmp_path / "scenarios.sqlite3"
    store = SqliteScenarioStore(path)
    scenario = make_scenario()
    store.create("sc-int-4", "job-int-4", scenario.model_dump(mode="json"))
    run_job(store, "sc-int-4", deps, UnavailableProvider(), AgentConfig())
    before = stored_detail(store, "sc-int-4")
    store.close()

    reopened = SqliteScenarioStore(path)
    after = stored_detail(reopened, "sc-int-4")
    assert after["status"] == before["status"] == "partial"
    assert after["report"] == before["report"]
    assert after["bundle"] == before["bundle"]
    reopened.close()
