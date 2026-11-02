"""P18: prompt registry block + one repair attempt. Fake provider only, offline."""

from __future__ import annotations

import json

from climateadapt.agent import workflow
from climateadapt.agent.schemas import AgentConfig
from climateadapt.llm.prompts import (
    build_repair_request,
    build_report_request,
    format_evidence_block,
    format_registry_block,
)
from climateadapt.llm.provider import FakeProvider, LLMUsage
from climateadapt.llm.report import FALLBACK_GENERATOR
from climateadapt.llm.validator import validate_report
from report_helpers import (
    evidence_entry,
    make_llm_bundle,
    make_llm_chunks,
    make_llm_context,
    make_llm_manifest,
    make_llm_ranking,
    valid_report_dict,
)
from test_agent_workflow import draft_provider, make_deps, make_scenario, stub_tools


def codes(problems: list[str]) -> list[str]:
    return [p[1:].split("]", 1)[0] for p in problems]


# --- Registry block ---------------------------------------------------------


def test_registry_block_lists_exact_allowed_ids_values_and_dates():
    ctx = make_llm_context()
    chunk_ids = sorted(ctx.chunks)
    block = format_registry_block(ctx.registry, chunk_ids)

    # Every registry output id appears exactly as the validator expects.
    for output_id in ctx.registry.outputs:
        assert output_id in block
    # Historic invented ids are explicitly banned, not just absent.
    assert "environmental_bundle" in block
    assert "recommendations" in block
    assert "entries[" in block
    # Exact numbers with (output_id, field) pairs.
    assert "chirps_spi.spi = -0.517" in block
    assert "chirps_spi.window_total_mm = 76.87" in block
    assert "bundle.latitude = 30.43" in block
    # Ranking + constraints vocabulary.
    assert "ranking:test-drip" in block
    assert "constraints:test-flood" in block
    assert "no_water_source" in block
    # Evidence ids and allowed dates.
    assert chunk_ids[0] in block
    assert "2024-03" in block
    # One worked numbers[] example is embedded.
    assert '"numbers"' in block
    assert '"tool_output_id"' in block


def test_report_request_embeds_registry_block_when_provided():
    ctx = make_llm_context()
    block = format_registry_block(ctx.registry, sorted(ctx.chunks))
    request = build_report_request(
        bundle_json="{}",
        ranking_json="{}",
        evidence_block="()",
        generator_label="fake:test-model",
        registry_block=block,
    )

    user_text = request.messages[1].content
    assert "chirps_spi.spi = -0.517" in user_text
    assert block in user_text


def test_report_request_without_registry_stays_backward_compatible():
    request = build_report_request(
        bundle_json="{}",
        ranking_json="{}",
        evidence_block="()",
        generator_label="fake:test-model",
    )

    assert len(request.messages) == 2
    assert request.messages[0].role == "system"
    assert request.messages[1].role == "user"


# --- Evidence block: full citation fields ------------------------------------


def test_evidence_block_renders_full_citation_fields_verbatim():
    from climateadapt.rag.citations import build_citation

    manifest = make_llm_manifest()
    chunks = make_llm_chunks()[:1]
    citations = [build_citation(chunks[0], manifest.get(chunks[0].doc_id))]
    block = format_evidence_block(chunks, citations)

    assert f'chunk_id="{chunks[0].chunk_id}"' in block
    assert f"citation: {citations[0].formatted}" in block
    assert f"pages: {citations[0].pages}" in block
    assert f"landing_url: {citations[0].landing_url}" in block
    assert f"license: {citations[0].license}" in block
    assert f"license_status: {citations[0].license_status}" in block


def test_evidence_block_str_citations_keep_legacy_shape():
    chunks = make_llm_chunks()[:1]
    block = format_evidence_block(chunks, citations=["Legacy citation."])

    assert "citation: Legacy citation." in block
    assert "landing_url:" not in block


# --- Historic failure classes are still rejected -----------------------------


def test_historic_invented_tool_output_ids_are_rejected():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    draft["summary"]["tool_output_ids"] = ["environmental_bundle", "recommendations"]
    finding = draft["environmental_findings"][0]
    finding["tool_output_ids"] = ["environmental_bundle"]
    finding["numbers"] = [
        {
            "value": 76.87,
            "unit": "mm",
            "tool_output_id": "environmental_bundle",
            "field": "entries[0].result.window_total_mm",
        }
    ]
    draft["provenance_refs"] = ["environmental_bundle", "recommendations"]

    result = validate_report(draft, ctx)

    assert not result.valid
    assert codes(result.problems).count("unknown-tool-output") >= 4
    assert "missing-provenance" in codes(result.problems)


def test_historic_altered_citation_pages_are_rejected():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    draft["evidence"][0]["pages"] = "pp. 999-1000 (PDF index; no printed label)"

    result = validate_report(draft, ctx)

    assert not result.valid
    assert "citation-mismatch" in codes(result.problems)


def test_historic_undeclared_prose_number_is_rejected():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    finding = draft["environmental_findings"][0]
    finding["text"] = "CHIRPS SPI is -0.517 with an extra 42.5 anomaly."
    # numbers[] unchanged: 42.5 is nowhere in the registry.

    result = validate_report(draft, ctx)

    assert not result.valid
    assert "undeclared-number" in codes(result.problems)


def test_valid_draft_still_passes():
    ctx = make_llm_context()

    result = validate_report(valid_report_dict(ctx), ctx)

    assert result.valid, result.problems


# --- Repair request builder --------------------------------------------------


def test_repair_request_carries_problems_and_draft_excerpt():
    first = build_report_request(
        bundle_json="{}",
        ranking_json="{}",
        evidence_block="()",
        generator_label="fake:test-model",
    )
    problems = ["[unknown-tool-output] summary: 'x' is not a tool output."]
    repair = build_repair_request(first, '{"summary": "bad"}', problems)

    assert len(repair.messages) == 2
    assert repair.messages[0].content == first.messages[0].content
    assert "unknown-tool-output" in repair.messages[1].content
    assert '{"summary": "bad"}' in repair.messages[1].content
    assert repair.max_tokens == first.max_tokens


def test_repair_request_caps_problems_and_long_drafts():
    first = build_report_request(
        bundle_json="{}",
        ranking_json="{}",
        evidence_block="()",
        generator_label="fake:test-model",
    )
    problems = [f"[code-{i}] problem {i}" for i in range(50)]
    repair = build_repair_request(first, "x" * 50000, problems)

    user_text = repair.messages[1].content
    assert "code-0" in user_text
    assert "code-49" not in user_text  # capped, with an overflow marker
    assert "more problems" in user_text
    assert len(user_text) < 50000  # long draft excerpt is truncated
    assert "truncated" in user_text


# --- Workflow repair path ----------------------------------------------------


def test_repair_success_accepts_the_second_draft(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    bad = valid_report_dict(ctx)
    bad["summary"]["tool_output_ids"] = ["environmental_bundle"]
    good = valid_report_dict(ctx)
    provider = FakeProvider(
        [
            FakeProvider.with_text(
                json.dumps(bad),
                usage=LLMUsage(prompt_tokens=100, completion_tokens=50),
            )._script[0],
            FakeProvider.with_text(
                json.dumps(good),
                usage=LLMUsage(prompt_tokens=120, completion_tokens=60),
            )._script[0],
        ]
    )

    result = workflow.run_agent(
        make_scenario(),
        deps,
        provider,
        AgentConfig(max_llm_calls=2, max_repair_attempts=1),
    )

    assert result.status == "complete"
    assert result.report is not None and result.report.fallback is False
    assert result.llm_calls == 2
    assert result.prompt_tokens == 220  # 100 default + 120 repair
    assert any(w.startswith("[repair]") for w in result.warnings)
    assert "[repair-accepted]" in result.trace.validator_verdicts


def test_repair_failure_serves_the_labelled_fallback(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    bad = valid_report_dict(ctx)
    bad["summary"]["evidence_ids"] = [sorted(ctx.chunks)[1]]  # cited, not listed
    worse = valid_report_dict(ctx)
    worse["summary"]["evidence_ids"] = [sorted(ctx.chunks)[1]]
    provider = FakeProvider(
        [
            FakeProvider.with_text(json.dumps(bad))._script[0],
            FakeProvider.with_text(json.dumps(worse))._script[0],
        ]
    )

    result = workflow.run_agent(
        make_scenario(),
        deps,
        provider,
        AgentConfig(max_llm_calls=2, max_repair_attempts=1),
    )

    assert result.status == "partial"
    assert result.report is not None and result.report.fallback is True
    assert result.report.generator == FALLBACK_GENERATOR
    assert result.llm_calls == 2
    assert any(p.startswith("[missing-evidence-entry]") for p in result.problems)
    assert "[repair-accepted]" not in result.trace.validator_verdicts


def test_no_repair_by_default_single_call_falls_back(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    bad = valid_report_dict(ctx)
    bad["summary"]["evidence_ids"] = [sorted(ctx.chunks)[1]]  # cited, not listed
    provider = FakeProvider.with_text(json.dumps(bad))

    result = workflow.run_agent(make_scenario(), deps, provider)

    assert result.status == "partial"
    assert result.llm_calls == 1
    assert len(provider.requests) == 1
    assert AgentConfig().max_repair_attempts == 0


def test_fallback_reporter_still_self_validates_after_prompt_change():
    from climateadapt.llm.fallback import build_fallback_report

    ctx = make_llm_context()
    report = build_fallback_report(
        make_llm_bundle(),
        make_llm_ranking(),
        list(ctx.chunks.values()),
        ctx.manifest or make_llm_manifest(),
        ["[unknown-tool-output] summary: 'environmental_bundle' is not a tool output."],
    )

    assert report.generator == FALLBACK_GENERATOR
    assert report.fallback_note is not None
    assert "unknown-tool-output" in report.fallback_note
    check = validate_report(report, ctx, allow_fallback=True)
    assert check.valid, check.problems
    assert evidence_entry(list(ctx.chunks.values())[0], ctx.manifest)["chunk_id"]


# --- P22: efficacy rules, repair evidence, trace keeps drafts ------------------


def test_system_prompt_forbids_effect_wording_with_a_compliant_example():
    from climateadapt.llm.prompts import load_system_prompt

    system = load_system_prompt()

    assert "improves" in system
    assert "reduces" in system
    assert "saves" in system
    assert "Compliant narrative example" in system


def test_repair_request_includes_offending_text_and_matched_phrase():
    ctx = make_llm_context()
    draft = valid_report_dict(ctx)
    narrative = draft["ranked_recommendations"][0]["narrative"]
    narrative["text"] = (
        "Test drip (test-drip): ranked with score 0.85. "
        "It reduces water use."
    )
    problems = validate_report(draft, ctx).problems
    assert "efficacy-claim" in codes(problems)
    first = build_report_request(
        bundle_json="{}",
        ranking_json="{}",
        evidence_block="()",
        generator_label="fake:test-model",
    )

    repair = build_repair_request(first, json.dumps(draft), problems)

    user_text = repair.messages[1].content
    problem_lines = [
        line for line in user_text.splitlines() if line.startswith("- [efficacy-claim]")
    ]
    assert len(problem_lines) == 1
    assert "reduces" in problem_lines[0]
    assert "It reduces water use." in problem_lines[0]


def test_era5_mentioning_draft_is_accepted_end_to_end(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    draft = valid_report_dict(ctx)
    finding = draft["environmental_findings"][0]
    finding["text"] = (
        finding["text"] + " ERA5-Land agrees on the sign of the anomaly."
    )
    provider = FakeProvider.with_text(json.dumps(draft))

    result = workflow.run_agent(make_scenario(), deps, provider)

    assert result.status == "complete", result.problems
    assert result.report is not None and result.report.fallback is False


def test_trace_keeps_the_draft_and_repair_texts(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)
    ctx = make_llm_context(chunks=retrieved)
    bad = valid_report_dict(ctx)
    bad["summary"]["tool_output_ids"] = ["environmental_bundle"]
    good = valid_report_dict(ctx)
    provider = FakeProvider(
        [
            FakeProvider.with_text(json.dumps(bad))._script[0],
            FakeProvider.with_text(json.dumps(good))._script[0],
        ]
    )

    result = workflow.run_agent(
        make_scenario(),
        deps,
        provider,
        AgentConfig(max_llm_calls=2, max_repair_attempts=1),
    )

    assert result.status == "complete"
    assert "environmental_bundle" in result.trace.draft_text
    assert result.trace.repair_text != ""
    assert "environmental_bundle" not in result.trace.repair_text


# --- P23: strict numeric policy ----------------------------------------------


def test_system_prompt_states_the_strict_numeric_policy():
    from climateadapt.llm.prompts import load_system_prompt

    system = load_system_prompt()

    assert "ONLY if it appears" in system
    assert "the first ERA5-Land soil layer" in system
    assert "the dataset's native grid" in system
    assert "never write it as a number" in system
    assert "Compliant limitation example" in system


def test_registry_block_states_the_numeric_policy():
    ctx = make_llm_context()
    block = format_registry_block(ctx.registry, sorted(ctx.chunks))

    assert "write a numeral only if it appears above with exactly that value" in block
    assert "must be words, never digits" in block


def test_repair_request_tells_the_model_to_replace_numbers_with_words():
    first = build_report_request(
        bundle_json="{}",
        ranking_json="{}",
        evidence_block="()",
        generator_label="fake:test-model",
    )
    problems = [
        "[undeclared-number] limitations[2]: numeral '7.8' is not a declared "
        "tool-output value. Offending sentence: 'fallback 7.8 km'."
    ]

    repair = build_repair_request(first, '{"limitations": ["fallback 7.8 km"]}', problems)

    user_text = repair.messages[1].content
    assert (
        "replace the number with words or delete the sentence; "
        "do not add new numbers" in user_text
    )
    assert "fallback 7.8 km" in user_text


def test_trace_repair_text_stays_empty_without_a_repair(monkeypatch):
    deps, retrieved = make_deps()
    stub_tools(monkeypatch, retrieved)

    result = workflow.run_agent(make_scenario(), deps, draft_provider(retrieved))

    assert result.status == "complete"
    assert result.trace.draft_text != ""
    assert result.trace.repair_text == ""
