"""P23: statement-level acceptance. Fake provider only, offline."""

from __future__ import annotations

import json

from climateadapt.agent import workflow
from climateadapt.agent.schemas import AgentConfig
from climateadapt.llm.composite import (
    build_composite,
    count_model_statements,
    group_by_statement,
    statement_locations,
)
from climateadapt.llm.fallback import build_fallback_report
from climateadapt.llm.provider import FakeProvider
from climateadapt.llm.report import Report
from climateadapt.llm.validator import validate_report
from report_helpers import (
    make_llm_bundle,
    make_llm_context,
    make_llm_manifest,
    make_llm_ranking,
    valid_report_dict,
)
from test_agent_workflow import make_deps, make_scenario, stub_tools


def codes(problems: list[str]) -> list[str]:
    return [p[1:].split("]", 1)[0] for p in problems]


# --- Grouping ---------------------------------------------------------------


def test_group_by_statement_merges_paths_and_flags_the_rest():
    grouped, rest = group_by_statement(
        [
            "[undeclared-number] limitations[2]: numeral '7.8' is undeclared.",
            "[efficacy-claim] ranked_recommendations[0]: effects.",
            "[unknown-tool-output] ranked_recommendations[0].narrative: ghost.",
            "[missing-evidence-entry] 'doc:1' is cited but not listed.",
            "[missing-provenance] 'ghost' is not a tool output.",
            "[schema] limitations: Field required.",
        ]
    )

    assert grouped == {
        "limitations[2]": ["undeclared-number"],
        "ranked_recommendations[0]": ["efficacy-claim", "unknown-tool-output"],
    }
    assert codes(rest) == [
        "missing-evidence-entry",
        "missing-provenance",
        "schema",
    ]


def test_statement_locations_use_the_validator_vocabulary():
    ctx = make_llm_context()
    report = Report.model_validate(valid_report_dict(ctx))

    assert statement_locations(report) == [
        "summary",
        "environmental_findings[0]",
        "ranked_recommendations[0]",
        "excluded_options[0]",
        "limitations[0]",
        "limitations[1]",
        "assumptions[0]",
        "data_coverage",
    ]


def test_fallback_report_carries_platform_origins():
    ctx = make_llm_context()
    report = build_fallback_report(
        make_llm_bundle(),
        make_llm_ranking(),
        list(ctx.chunks.values()),
        ctx.manifest or make_llm_manifest(),
        ["[undeclared-number] limitations[2]: numeral '7.8' is undeclared."],
    )

    assert report.acceptance == "fallback"
    assert report.replaced_statements == {}
    assert report.dropped_statements == {}
    assert set(report.statement_origins) == set(statement_locations(report))
    assert set(report.statement_origins.values()) == {"platform"}
    assert count_model_statements(report) == (0, len(report.statement_origins))


# --- Composite matching rules -----------------------------------------------


def test_unknown_intervention_is_dropped_not_shipped():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    rec = draft["ranked_recommendations"][0]
    rec["intervention_id"] = "ghost"
    rec["narrative"]["tool_output_ids"] = ["ranking:ghost"]
    problems = validate_report(draft, ctx).problems
    assert "unknown-intervention" in codes(problems)
    model = Report.model_validate(draft)
    fallback = build_fallback_report(
        make_llm_bundle(), make_llm_ranking(), list(ctx.chunks.values()),
        ctx.manifest or make_llm_manifest(), problems,
    )

    result = build_composite(model, fallback, problems)

    assert result is not None
    assert result.dropped == {
        "ranked_recommendations[0]": ["unknown-intervention", "unknown-tool-output"]
    }
    assert result.report.ranked_recommendations == []
    assert "ranked_recommendations[0]" not in result.origins


def test_positional_overflow_limitation_is_dropped():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    draft["limitations"] = [
        "Kept limitation alpha.",
        "Kept limitation beta.",
        "Kept limitation gamma.",
        "Kept limitation delta.",
        "Kept limitation epsilon.",
        "Only 12 stations were available.",
    ]
    problems = validate_report(draft, ctx).problems
    assert codes(problems) == ["undeclared-number"]
    model = Report.model_validate(draft)
    fallback = build_fallback_report(
        make_llm_bundle(), make_llm_ranking(), list(ctx.chunks.values()),
        ctx.manifest or make_llm_manifest(), problems,
    )
    assert len(fallback.limitations) == 5  # index 5 has no counterpart

    result = build_composite(model, fallback, problems)

    assert result is not None
    assert result.dropped == {"limitations[5]": ["undeclared-number"]}
    assert len(result.report.limitations) == 5
    assert "Only 12 stations" not in json.dumps(result.report.model_dump(mode="json"))


def test_non_statement_problem_forces_full_fallback():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    draft["summary"]["evidence_ids"] = [sorted(ctx.chunks)[1]]  # cited, not listed
    problems = validate_report(draft, ctx).problems
    assert "missing-evidence-entry" in codes(problems)
    model = Report.model_validate(draft)
    fallback = build_fallback_report(
        make_llm_bundle(), make_llm_ranking(), list(ctx.chunks.values()),
        ctx.manifest or make_llm_manifest(), problems,
    )

    assert build_composite(model, fallback, problems) is None


# --- Workflow: one failing statement yields ai-partial -----------------------


def test_fully_valid_draft_is_stamped_ai_accepted(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    provider = FakeProvider.with_text(json.dumps(valid_report_dict(ctx)))

    result = workflow.run_agent(make_scenario(), deps, provider)

    assert result.status == "complete"
    assert result.problems == []
    assert result.report is not None and result.report.fallback is False
    assert result.report.acceptance == "ai-accepted"
    assert result.report.replaced_statements == {}
    assert result.report.dropped_statements == {}
    assert set(result.report.statement_origins.values()) == {"model"}
    assert count_model_statements(result.report) == (8, 8)
    assert "[accepted]" in result.trace.validator_verdicts


def test_one_failing_statement_yields_ai_partial(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    draft = valid_report_dict(ctx)
    draft["limitations"].append("Only 12 stations were available.")
    provider = FakeProvider.with_text(json.dumps(draft))

    result = workflow.run_agent(make_scenario(), deps, provider)

    assert result.status == "complete"
    assert result.problems == []
    report = result.report
    assert report is not None and report.fallback is False
    assert report.acceptance == "ai-partial"
    assert report.dropped_statements == {}
    assert report.replaced_statements == {"limitations[2]": ["undeclared-number"]}
    assert report.statement_origins == {
        "summary": "model",
        "environmental_findings[0]": "model",
        "ranked_recommendations[0]": "model",
        "excluded_options[0]": "model",
        "limitations[0]": "model",
        "limitations[1]": "model",
        "limitations[2]": "platform",
        "assumptions[0]": "model",
        "data_coverage": "model",
    }
    assert count_model_statements(report) == (8, 9)
    # The failing statement is platform-written, everything else is the model's.
    assert report.limitations[2] == (
        "Benefit, cost and risk are unknown unless the catalog cites a source."
    )
    assert report.summary.text == draft["summary"]["text"]
    assert any("[composite]" in w and "8 of 9" in w for w in result.warnings)
    assert "[composite-accepted]" in result.trace.validator_verdicts
    check = validate_report(report, ctx)
    assert check.valid, check.problems


def test_missing_section_yields_full_fallback(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    bad = valid_report_dict(ctx)
    bad["limitations"] = []
    provider = FakeProvider(
        [
            FakeProvider.with_text(json.dumps(bad))._script[0],
            FakeProvider.with_text(json.dumps(bad))._script[0],
        ]
    )

    result = workflow.run_agent(
        make_scenario(), deps, provider,
        AgentConfig(max_llm_calls=2, max_repair_attempts=1),
    )

    assert result.status == "partial"
    assert result.llm_calls == 2
    assert result.report is not None and result.report.fallback is True
    assert result.report.acceptance == "fallback"
    assert set(result.report.statement_origins.values()) == {"platform"}
    assert "[composite-accepted]" not in result.trace.validator_verdicts


def test_composite_that_fails_revalidation_yields_full_fallback(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    draft = valid_report_dict(ctx)
    draft["evidence"] = [draft["evidence"][0], dict(draft["evidence"][0])]
    provider = FakeProvider.with_text(json.dumps(draft))

    result = workflow.run_agent(make_scenario(), deps, provider)

    assert result.status == "partial"
    assert result.report is not None and result.report.fallback is True
    assert result.report.acceptance == "fallback"
    assert "[composite-accepted]" not in result.trace.validator_verdicts


def test_worse_repair_uses_the_first_draft_as_base(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    first = valid_report_dict(ctx)
    first["summary"]["text"] = "First draft summary."
    first["limitations"].append("First-only bad limitation 12 stations.")
    repair = valid_report_dict(ctx)
    repair["summary"]["text"] = "Repair draft summary."
    repair["limitations"].append("Repair bad one 12 stations.")
    repair["limitations"].append("Repair bad two 13 stations.")
    provider = FakeProvider(
        [
            FakeProvider.with_text(json.dumps(first))._script[0],
            FakeProvider.with_text(json.dumps(repair))._script[0],
        ]
    )

    result = workflow.run_agent(
        make_scenario(), deps, provider,
        AgentConfig(max_llm_calls=2, max_repair_attempts=1),
    )

    assert result.status == "complete"
    assert result.llm_calls == 2
    assert result.report is not None and result.report.fallback is False
    assert result.report.acceptance == "ai-partial"
    assert result.report.summary.text == "First draft summary."
    assert result.report.replaced_statements == {
        "limitations[2]": ["undeclared-number"]
    }
    assert any("Base: first draft" in w for w in result.warnings)


def test_historic_failures_are_replaced_never_shipped(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    draft = valid_report_dict(ctx)
    draft["summary"]["tool_output_ids"] = ["environmental_bundle"]
    draft["evidence"][0]["pages"] = "pp. 999-1000 (PDF index; no printed label)"
    finding = draft["environmental_findings"][0]
    finding["text"] = "CHIRPS SPI is -0.517 with an extra 42.5 anomaly."
    narrative = draft["ranked_recommendations"][0]["narrative"]
    narrative["text"] = (
        "Test drip (test-drip): ranked with score 0.85. It reduces water use."
    )
    provider = FakeProvider.with_text(json.dumps(draft))

    result = workflow.run_agent(make_scenario(), deps, provider)

    assert result.status == "complete"
    report = result.report
    assert report is not None and report.fallback is False
    assert report.acceptance == "ai-partial"
    blob = json.dumps(report.model_dump(mode="json"))
    assert "environmental_bundle" not in blob
    assert "999-1000" not in blob
    assert "42.5" not in blob
    assert "reduces water use" not in blob
    chunk_id = draft["evidence"][0]["chunk_id"]
    assert report.replaced_statements == {
        "summary": ["unknown-tool-output"],
        "environmental_findings[0]": ["undeclared-number"],
        "ranked_recommendations[0]": ["efficacy-claim"],
        f"evidence[{chunk_id}]": ["citation-mismatch"],
    }
    check = validate_report(report, ctx)
    assert check.valid, check.problems
