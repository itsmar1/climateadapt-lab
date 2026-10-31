"""Offline tests for the fixed agent pipeline. No network, no real credentials."""

from __future__ import annotations

import copy
import json

import pytest

from climateadapt.agent import workflow
from climateadapt.agent.schemas import AgentConfig, AgentDeps, AgentScenario
from climateadapt.agent.tools import RetrievalToolResult
from climateadapt.agent.trace import save_trace
from climateadapt.agent.workflow import _Abort, _enter, run_agent
from climateadapt.data.errors import OutsideCoverageError
from climateadapt.llm.provider import FakeProvider, LLMRateLimitError, LLMUsage
from climateadapt.rag.models import RetrievedChunk
from climateadapt.recommend.schema import RecommendationResponse
from climateadapt.schemas_era5 import EnvironmentalBundleResponse
from recommend_helpers import make_catalog
from report_helpers import (
    make_llm_bundle,
    make_llm_chunks,
    make_llm_context,
    make_llm_manifest,
    make_llm_pages,
    make_llm_ranking,
    valid_report_dict,
)


def make_scenario(**overrides) -> AgentScenario:
    scenario = {
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
    scenario.update(overrides)
    return AgentScenario.model_validate(scenario)


def make_deps(retrieved_count: int = 2) -> tuple[AgentDeps, list]:
    """Deps with stubbed clients (bundle tool is stubbed; nothing needs them)."""
    chunks = make_llm_chunks()
    return (
        AgentDeps(
            chirps=None,
            era5=None,
            chunks=chunks,
            manifest=make_llm_manifest(),
            pages_by_doc=make_llm_pages(),
            catalog=make_catalog(),
        ),
        chunks[:retrieved_count],
    )


def stub_tools(monkeypatch, retrieved, *, ranking=None, bundle=None):
    """Stub the network/client tools; retrieval returns the given chunks."""
    bundle_response = EnvironmentalBundleResponse.model_validate(bundle or make_llm_bundle())
    ranking_response = RecommendationResponse.model_validate(ranking or make_llm_ranking())
    hits = [
        RetrievedChunk(
            chunk=chunk, score=1.0 - 0.1 * rank, rank=rank + 1,
            component_ranks={"bm25": rank + 1},
            component_scores={"bm25": 1.0 - 0.1 * rank},
        )
        for rank, chunk in enumerate(retrieved)
    ]
    monkeypatch.setattr(workflow, "get_environmental_bundle", lambda *a, **k: bundle_response)
    monkeypatch.setattr(workflow, "rank_adaptation_options", lambda *a, **k: ranking_response)
    monkeypatch.setattr(
        workflow,
        "retrieve_evidence",
        lambda *a, **k: RetrievalToolResult(query="q", retriever="bm25", hits=hits),
    )
    return bundle_response, ranking_response


def draft_provider(retrieved, usage=None) -> FakeProvider:
    ctx = make_llm_context(chunks=retrieved)
    usage = usage or LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    return FakeProvider.with_text(json.dumps(valid_report_dict(ctx)), usage=usage)


# --- Happy path -------------------------------------------------------------


def test_happy_path_accepts_and_traces_everything(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    provider = draft_provider(retrieved)

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "complete"
    assert result.report is not None
    assert result.report.fallback is False
    assert result.problems == []
    assert result.warnings == []
    assert result.llm_calls == 1
    assert result.tool_calls_made == 4
    assert provider.requests[0].temperature is None
    assert provider.requests[0].max_tokens == 16000

    trace = result.trace
    assert trace is not None
    assert trace.outcome == "complete"
    assert [s.name for s in trace.stages] == [
        "validate_inputs", "bundle", "retrieval", "ranking",
        "draft", "validate", "finalize",
    ]
    assert all(s.status == "ok" for s in trace.stages)
    assert [c.name for c in trace.tool_calls] == [
        "get_environmental_bundle", "retrieve_evidence",
        "rank_adaptation_options", "validate_report",
    ]
    assert all(c.ok for c in trace.tool_calls)
    assert trace.validator_verdicts == ["[accepted]"]
    assert trace.config["temperature"] is None
    assert trace.config["seed"] == "unsupported-by-model; not set"
    assert trace.component_versions["model"] == "fake"
    assert trace.component_versions["catalog_version"] == "1"
    assert trace.usage == {"prompt_tokens": 100, "completion_tokens": 50, "llm_calls": 1}

    dumped = trace.model_dump_json()
    assert "Bearer" not in dumped
    assert retrieved[0].text not in dumped  # ids + scores only, never passage text
    assert retrieved[0].chunk_id in dumped


def test_usage_is_accumulated_from_the_provider(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    provider = FakeProvider.with_text(
        json.dumps(valid_report_dict(ctx)),
        usage=LLMUsage(prompt_tokens=120, completion_tokens=60, total_tokens=180),
    )

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "complete"
    assert (result.prompt_tokens, result.completion_tokens) == (120, 60)
    assert result.trace.usage["prompt_tokens"] == 120


# --- Failure policy ---------------------------------------------------------


def test_validator_rejection_yields_the_labelled_fallback(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    draft = valid_report_dict(ctx)
    draft["summary"]["text"] = "Extreme drought everywhere."
    provider = FakeProvider.with_text(json.dumps(draft))

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "partial"
    assert result.report is not None
    assert result.report.fallback is True
    assert result.report.generator == "deterministic-fallback"
    assert any(p.startswith("[drought-label]") for p in result.problems)
    assert any("drought-label" in v for v in result.trace.validator_verdicts)
    assert result.trace.outcome == "partial"


def test_provider_error_yields_the_labelled_fallback(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    provider = FakeProvider([LLMRateLimitError("limited")])

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "partial"
    assert result.report is not None and result.report.fallback is True
    assert any(p.startswith("[provider-rate-limit]") for p in result.problems)
    assert result.llm_calls == 0
    assert [s.name for s in result.trace.stages if s.status == "skipped"] == ["validate"]


def test_bundle_failure_fails_without_a_report(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    monkeypatch.setattr(
        workflow,
        "get_environmental_bundle",
        lambda *a, **k: (_ for _ in ()).throw(
            OutsideCoverageError("68N is outside CHIRPS coverage.")
        ),
    )
    provider = FakeProvider.with_text("{}")

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "failed"
    assert result.report is None
    assert any(p.startswith("[outside_coverage]") for p in result.problems)
    assert provider.requests == []
    assert [s.name for s in result.trace.stages if s.status == "skipped"] == [
        "retrieval", "ranking", "draft", "validate",
    ]


def test_retrieval_failure_proceeds_without_evidence(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    monkeypatch.setattr(
        workflow, "retrieve_evidence",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("index gone")),
    )
    ctx = make_llm_context(chunks=retrieved)
    draft = valid_report_dict(ctx)
    draft["summary"]["evidence_ids"] = []
    draft["ranked_recommendations"][0]["narrative"]["evidence_ids"] = []
    draft["evidence"] = []
    provider = FakeProvider.with_text(json.dumps(draft))

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "complete"
    assert any(w.startswith("[retrieval-error]") for w in result.warnings)
    assert result.report.evidence == []


def test_ranking_failure_fails_the_run(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    monkeypatch.setattr(
        workflow, "rank_adaptation_options",
        lambda *a, **k: (_ for _ in ()).throw(KeyError("ghost-doc")),
    )
    provider = FakeProvider.with_text("{}")

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "failed"
    assert result.report is None
    assert any(p.startswith("[ranking-error]") for p in result.problems)
    assert provider.requests == []


def test_invalid_scenario_fails_before_any_work(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    provider = FakeProvider.with_text("{}")

    result = run_agent({"latitude": "north"}, deps, provider)

    assert result.status == "failed"
    assert result.report is None
    assert any(p.startswith("[invalid-scenario]") for p in result.problems)
    assert result.tool_calls_made == 0
    assert provider.requests == []


# --- Limits -----------------------------------------------------------------


def test_max_tool_calls_aborts_to_a_partial_fallback(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    provider = FakeProvider.with_text("{}")

    result = run_agent(
        make_scenario(), deps, provider, AgentConfig(max_tool_calls=1)
    )

    assert result.status == "partial"
    assert result.report is not None and result.report.fallback is True
    assert any(p.startswith("[max-tool-calls]") for p in result.problems)
    assert provider.requests == []  # the draft stage never ran


def test_max_steps_aborts_to_a_partial_fallback(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    provider = FakeProvider.with_text("{}")

    result = run_agent(make_scenario(), deps, provider, AgentConfig(max_steps=3))

    assert result.status == "partial"
    assert any(p.startswith("[max-steps]") for p in result.problems)
    assert provider.requests == []


def test_token_budget_discards_an_over_budget_draft(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    provider = FakeProvider.with_text(
        json.dumps(valid_report_dict(ctx)),
        usage=LLMUsage(prompt_tokens=90000, completion_tokens=20000),
    )

    result = run_agent(
        make_scenario(), deps, provider, AgentConfig(token_budget=100000)
    )

    assert result.status == "partial"
    assert result.report is not None and result.report.fallback is True
    assert any(p.startswith("[token-budget]") for p in result.problems)


def test_total_timeout_aborts_deterministically(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    calls = {"n": 0}

    def fake_clock():
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else 1000.0

    monkeypatch.setattr("climateadapt.agent.workflow.time.monotonic", fake_clock)
    provider = FakeProvider.with_text("{}")

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "failed"
    assert result.report is None
    assert any(p.startswith("[total-timeout]") for p in result.problems)
    assert provider.requests == []


def test_loop_detection_rejects_a_revisited_stage():
    ledger = {"bundle"}
    with pytest.raises(_Abort) as excinfo:
        _enter(ledger, "bundle")
    assert excinfo.value.code == "loop-detected"
    _enter(ledger, "retrieval")
    assert ledger == {"bundle", "retrieval"}


# --- Trace ------------------------------------------------------------------


def test_trace_saves_and_round_trips(tmp_path, monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    provider = draft_provider(retrieved)

    result = run_agent(make_scenario(), deps, provider)
    path = save_trace(result.trace, tmp_path / "trace.json")

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["outcome"] == "complete"


def test_accepted_draft_matches_a_deep_copy(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    draft = copy.deepcopy(valid_report_dict(ctx))
    provider = FakeProvider.with_text(json.dumps(draft))

    result = run_agent(make_scenario(), deps, provider)

    assert result.status == "complete"
    assert result.report.summary.text == draft["summary"]["text"]
