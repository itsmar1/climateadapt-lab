"""Tests for capture-from-run mode (P25). No network, no credentials.

Builds a synthetic accepted run + trace in memory, recombines them with a
synthetic deterministic bundle/ranking via
``scripts.capture_demo_snapshot.build_detail_from_run``, and checks the
assembled detail plus the failure-closed rejections.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from capture_demo_snapshot import build_detail_from_run  # noqa: E402
from climateadapt.llm.validator import validate_report  # noqa: E402
from report_helpers import (  # noqa: E402
    make_llm_bundle,
    make_llm_context,
    make_llm_ranking,
    valid_report_dict,
)
from test_integration_workflow import make_scenario  # noqa: E402

ORIGINS_ALL_MODEL = {
    "summary": "model",
    "environmental_findings[0]": "model",
    "ranked_recommendations[0]": "model",
    "excluded_options[0]": "model",
    "limitations[0]": "model",
    "limitations[1]": "model",
    "assumptions[0]": "model",
    "data_coverage": "model",
}

WARNING = "[repair] First draft rejected (1 problems); repair accepted."


def make_run_data() -> dict:
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    draft["acceptance"] = "ai-accepted"
    draft["statement_origins"] = dict(ORIGINS_ALL_MODEL)
    draft["replaced_statements"] = {}
    draft["dropped_statements"] = {}
    assert validate_report(draft, ctx).valid
    return {
        "status": "complete",
        "problems": [],
        "warnings": [WARNING],
        "report": draft,
    }


def make_trace_data() -> dict:
    scenario = make_scenario().model_dump(mode="json")
    stages = [
        {"name": name, "status": "ok", "started_at": "2026-11-02T20:20:45+00:00",
         "duration_ms": 10.0, "detail": "", "error_code": None}
        for name in (
            "validate_inputs", "bundle", "retrieval", "ranking", "draft",
            "validate", "finalize",
        )
    ]
    return {
        "run_id": "abc123",
        "agent_version": 1,
        "started_at": "2026-11-02T20:20:45+00:00",
        "ended_at": "2026-11-02T20:22:27+00:00",
        "duration_ms_total": 101781.0,
        "scenario": scenario,
        "config": {"max_llm_calls": 2, "max_repair_attempts": 1, "max_tokens": 16000},
        "component_versions": {
            "agent": "1",
            "report_schema": "1",
            "model": "baseten:meta-models/muse-spark-open-1026",
        },
        "stages": stages,
        "tool_calls": [
            {"name": "get_environmental_bundle", "ok": True, "duration_ms": 5.0,
             "input_summary": "{}", "output_summary": "statuses ok",
             "error_code": None},
            {"name": "validate_report", "ok": True, "duration_ms": 1.0,
             "input_summary": "", "output_summary": "verdict=accepted(repair)",
             "error_code": None},
        ],
        "validator_verdicts": [
            "[invalid-json] Draft is not valid JSON: truncated.",
            "[repair-accepted]",
        ],
        "draft_text": "SHOULD-BE-STRIPPED",
        "repair_text": "SHOULD-BE-STRIPPED",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "llm_calls": 2},
        "outcome": "complete",
        "problems": [],
        "warnings": [WARNING],
    }


def test_from_run_assembles_complete_detail():
    detail = build_detail_from_run(
        make_run_data(),
        make_trace_data(),
        bundle=make_llm_bundle(),
        ranking=make_llm_ranking(),
        validation_context=make_llm_context(),
        scenario_id="capture-synth-ai",
    )
    assert detail.status == "complete"
    assert detail.scenario_id == "capture-synth-ai"
    assert detail.job_id == "job-capture"
    assert detail.problems == []
    assert detail.warnings == [WARNING]
    assert detail.report is not None
    assert detail.report.fallback is False
    assert detail.report.acceptance == "ai-accepted"
    assert detail.report.statement_origins == ORIGINS_ALL_MODEL
    assert detail.trace is not None
    assert detail.trace.usage == {
        "prompt_tokens": 100, "completion_tokens": 50, "llm_calls": 2,
    }
    assert detail.trace.draft_text == ""
    assert detail.trace.repair_text == ""
    assert detail.trace.validator_verdicts[0].startswith("[invalid-json]")
    assert detail.trace.validator_verdicts[-1] == "[repair-accepted]"
    assert detail.trace.component_versions["model"] == (
        "baseten:meta-models/muse-spark-open-1026"
    )
    assert [s.name for s in detail.trace.stages] == [
        "validate_inputs", "bundle", "retrieval", "ranking", "draft",
        "validate", "finalize",
    ]


def test_from_run_rejects_fallback_report():
    run_data = make_run_data()
    run_data["report"]["fallback"] = True
    run_data["report"]["acceptance"] = "fallback"
    with pytest.raises(ValueError, match="not an accepted model report"):
        build_detail_from_run(
            run_data,
            make_trace_data(),
            bundle=make_llm_bundle(),
            ranking=make_llm_ranking(),
            validation_context=make_llm_context(),
            scenario_id="capture-x",
        )


def test_from_run_rejects_nonzero_problems():
    run_data = make_run_data()
    run_data["problems"] = ["[draft-rejected] bad"]
    with pytest.raises(ValueError, match="not zero"):
        build_detail_from_run(
            run_data,
            make_trace_data(),
            bundle=make_llm_bundle(),
            ranking=make_llm_ranking(),
            validation_context=make_llm_context(),
            scenario_id="capture-x",
        )


def test_from_run_rejects_report_failing_revalidation():
    run_data = make_run_data()
    run_data["report"]["summary"]["numbers"] = [
        {"value": 999.0, "unit": None, "tool_output_id": "bundle",
         "field": "latitude"}
    ]
    with pytest.raises(ValueError, match="fails re-validation"):
        build_detail_from_run(
            run_data,
            make_trace_data(),
            bundle=make_llm_bundle(),
            ranking=make_llm_ranking(),
            validation_context=make_llm_context(),
            scenario_id="capture-x",
        )
