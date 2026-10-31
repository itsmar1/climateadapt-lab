"""Fixed sequential agent pipeline with hard limits and full tracing.

Stages: validate_inputs -> bundle -> retrieval -> ranking -> draft (LLM) ->
validate -> finalize. Every stage runs at most once, in order; there is no
planner, no loop, and no path around the P09 validator. Outcomes:

* ``complete`` — the model draft passed validation and is returned.
* ``partial`` — any tool failure, limit breach, or invalid draft: the labelled
  deterministic fallback built from whatever deterministic outputs exist.
* ``failed`` — no report could be grounded (bad inputs, no bundle, no ranking).

Nothing is ever fabricated: missing values stay missing and are reported.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from climateadapt.agent.schemas import (
    AGENT_VERSION,
    AgentConfig,
    AgentDeps,
    AgentScenario,
)
from climateadapt.agent.tools import (
    BundleToolParams,
    RankingToolParams,
    RetrievalToolParams,
    get_environmental_bundle,
    rank_adaptation_options,
    retrieve_evidence,
    validate_report_tool,
)
from climateadapt.agent.trace import (
    RunTrace,
    StageRecord,
    ToolCallRecord,
    summarize,
)
from climateadapt.api.errors import domain_error_status
from climateadapt.llm.fallback import build_fallback_report
from climateadapt.llm.prompts import build_report_request, format_evidence_block
from climateadapt.llm.provider import (
    LLMAuthError,
    LLMError,
    LLMInvalidResponseError,
    LLMProvider,
    LLMRateLimitError,
    LLMTimeoutError,
)
from climateadapt.llm.report import REPORT_SCHEMA_VERSION, Report, build_registry
from climateadapt.llm.service import parse_model_json
from climateadapt.llm.validator import ValidationContext
from climateadapt.rag.citations import build_citation
from climateadapt.rag.models import Chunk

STAGES = (
    "validate_inputs",
    "bundle",
    "retrieval",
    "ranking",
    "draft",
    "validate",
    "finalize",
)


class _Abort(Exception):
    """Internal control flow: stop the pipeline with a machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail)
        self.code = code


def _enter(ledger: set[str], stage: str) -> None:
    """Loop detection: no stage may run twice in one run."""
    if stage in ledger:
        raise _Abort("loop-detected", f"Stage {stage!r} was entered twice.")
    ledger.add(stage)


def _provider_code(exc: LLMError) -> str:
    if isinstance(exc, LLMRateLimitError):
        return "provider-rate-limit"
    if isinstance(exc, LLMTimeoutError):
        return "provider-timeout"
    if isinstance(exc, LLMAuthError):
        return "provider-auth"
    if isinstance(exc, LLMInvalidResponseError):
        return "provider-refusal"
    return "provider-error"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class AgentResult:
    status: str  # "complete" | "partial" | "failed"
    report: Report | None
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: RunTrace | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    tool_calls_made: int = 0
    bundle: Any = None  # EnvironmentalBundleResponse (kept for API persistence)
    ranking: Any = None  # RecommendationResponse (kept for API persistence)


def _record_stage(
    trace: RunTrace,
    name: str,
    status: str,
    started_at: str,
    started_mono: float,
    detail: str = "",
    error_code: str | None = None,
) -> None:
    trace.stages.append(
        StageRecord(
            name=name,
            status=status,
            started_at=started_at,
            duration_ms=(time.monotonic() - started_mono) * 1000,
            detail=detail,
            error_code=error_code,
        )
    )


def run_agent(
    scenario: AgentScenario | dict[str, Any],
    deps: AgentDeps,
    provider: LLMProvider,
    config: AgentConfig | None = None,
) -> AgentResult:
    """Run the fixed pipeline once. Bounded, traced, never fabricating."""
    config = config or AgentConfig()
    t0 = time.monotonic()
    trace = RunTrace(
        run_id=uuid.uuid4().hex,
        agent_version=AGENT_VERSION,
        started_at=_now(),
        config={**config.model_dump(), "seed": "unsupported-by-model; not set"},
        component_versions={
            "agent": str(AGENT_VERSION),
            "report_schema": str(REPORT_SCHEMA_VERSION),
            "model": provider.label,
        },
    )
    result = AgentResult(status="failed", report=None, trace=trace)
    ledger: set[str] = set()

    def check_bounds(stage: str) -> None:
        if len(ledger) >= config.max_steps:
            raise _Abort("max-steps", f"Step budget ({config.max_steps}) exhausted.")
        if time.monotonic() - t0 >= config.total_timeout_seconds:
            raise _Abort(
                "total-timeout",
                f"Total budget ({config.total_timeout_seconds}s) exhausted.",
            )
        _enter(ledger, stage)

    def check_tool_budget() -> None:
        if result.tool_calls_made >= config.max_tool_calls:
            raise _Abort(
                "max-tool-calls", f"Tool budget ({config.max_tool_calls}) exhausted."
            )

    parsed: AgentScenario | None = None
    bundle = None
    ranking = None
    retrieved: list[Chunk] = []

    try:
        # 1. validate_inputs (before any work; not subject to the deadline).
        _enter(ledger, "validate_inputs")
        started_at = _now()
        started_mono = time.monotonic()
        try:
            parsed = (
                scenario
                if isinstance(scenario, AgentScenario)
                else AgentScenario.model_validate(scenario)
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            _record_stage(
                trace, "validate_inputs", "failed", started_at, started_mono,
                error_code="invalid-scenario",
            )
            result.problems.append(
                f"[invalid-scenario] {'.'.join(map(str, first['loc']))}: {first['msg']}"
            )
            raise _Abort("invalid-scenario") from exc
        if deps.manifest is None or deps.catalog is None:
            _record_stage(
                trace, "validate_inputs", "failed", started_at, started_mono,
                error_code="missing-deps",
            )
            result.problems.append("[missing-deps] Manifest and catalog are required.")
            raise _Abort("missing-deps")
        trace.scenario = parsed.model_dump()
        trace.component_versions["catalog_version"] = str(deps.catalog.catalog_version)
        _record_stage(trace, "validate_inputs", "ok", started_at, started_mono)
        assert parsed is not None

        # 2. bundle.
        check_bounds("bundle")
        started_at = _now()
        started_mono = time.monotonic()
        check_tool_budget()
        try:
            bundle = get_environmental_bundle(
                BundleToolParams(
                    latitude=parsed.latitude,
                    longitude=parsed.longitude,
                    target_end_month=parsed.target_end_month,
                    timescale_months=parsed.timescale_months,
                    reference_start_year=parsed.reference_start_year,
                    reference_end_year=parsed.reference_end_year,
                    min_reference_years=parsed.min_reference_years,
                    land_fallback_max_km=parsed.land_fallback_max_km,
                    indicators=list(parsed.indicators),
                ),
                deps.chirps,
                deps.era5,
            )
        except Exception as exc:  # any tool failure is reportable
            mapped = domain_error_status(exc)
            code = mapped[1] if mapped else "bundle-error"
            result.tool_calls_made += 1
            trace.tool_calls.append(
                ToolCallRecord(
                    name="get_environmental_bundle", ok=False,
                    duration_ms=(time.monotonic() - started_mono) * 1000,
                    error_code=code,
                )
            )
            _record_stage(
                trace, "bundle", "failed", started_at, started_mono,
                detail=str(exc)[:300], error_code=code,
            )
            result.problems.append(f"[{code}] Environmental bundle failed: {exc}")
            raise _Abort(code) from exc
        result.tool_calls_made += 1
        result.bundle = bundle
        statuses = {entry.indicator: entry.status for entry in bundle.entries}
        trace.tool_calls.append(
            ToolCallRecord(
                name="get_environmental_bundle", ok=True,
                duration_ms=(time.monotonic() - started_mono) * 1000,
                input_summary=summarize(BundleToolParams(
                    latitude=parsed.latitude, longitude=parsed.longitude,
                    target_end_month=parsed.target_end_month,
                    timescale_months=parsed.timescale_months,
                    reference_start_year=parsed.reference_start_year,
                    reference_end_year=parsed.reference_end_year,
                    min_reference_years=parsed.min_reference_years,
                    land_fallback_max_km=parsed.land_fallback_max_km,
                    indicators=list(parsed.indicators),
                ).model_dump_json()),
                output_summary=summarize(
                    f"statuses={statuses} " + bundle.model_dump_json()
                ),
            )
        )
        _record_stage(
            trace, "bundle", "ok", started_at, started_mono, detail=f"statuses={statuses}"
        )

        # 3. retrieval (failure is non-fatal: proceed without evidence).
        check_bounds("retrieval")
        started_at = _now()
        started_mono = time.monotonic()
        check_tool_budget()
        try:
            retrieval = retrieve_evidence(
                RetrievalToolParams(
                    query=parsed.query,
                    top_k=parsed.top_k,
                    exclude_reference=parsed.exclude_reference,
                ),
                deps.chunks,
                deps.dense_retriever,
            )
            retrieved = [hit.chunk for hit in retrieval.hits]
        except Exception as exc:  # retrieval failure is a warning
            result.tool_calls_made += 1
            trace.tool_calls.append(
                ToolCallRecord(
                    name="retrieve_evidence", ok=False,
                    duration_ms=(time.monotonic() - started_mono) * 1000,
                    input_summary=summarize(f"query={parsed.query!r} top_k={parsed.top_k}"),
                    error_code="retrieval-error",
                )
            )
            _record_stage(
                trace, "retrieval", "failed", started_at, started_mono,
                detail="Proceeding without evidence.", error_code="retrieval-error",
            )
            result.warnings.append(f"[retrieval-error] Retrieval failed: {exc}")
            retrieved = []
        else:
            result.tool_calls_made += 1
            trace.tool_calls.append(
                ToolCallRecord(
                    name="retrieve_evidence", ok=True,
                    duration_ms=(time.monotonic() - started_mono) * 1000,
                    input_summary=summarize(f"query={parsed.query!r} top_k={parsed.top_k}"),
                    output_summary=summarize(
                        f"retriever={retrieval.retriever} hits="
                        + ",".join(
                            f"{h.chunk.chunk_id}@{h.score:.3f}" for h in retrieval.hits
                        )
                    ),
                )
            )
            _record_stage(
                trace, "retrieval", "ok", started_at, started_mono,
                detail=f"{len(retrieved)} passages via {retrieval.retriever}",
            )
            if not retrieved:
                result.warnings.append("[retrieval-empty] No passages retrieved.")

        # 4. ranking (deterministic; required to ground recommendations).
        check_bounds("ranking")
        started_at = _now()
        started_mono = time.monotonic()
        check_tool_budget()
        assert deps.manifest is not None and deps.catalog is not None
        try:
            ranking = rank_adaptation_options(
                RankingToolParams(
                    crop=parsed.crop,
                    has_water_source=parsed.has_water_source,
                    has_irrigation_equipment=parsed.has_irrigation_equipment,
                    production_system=parsed.production_system,
                    season=parsed.season,
                    latitude=parsed.latitude,
                    longitude=parsed.longitude,
                ),
                bundle,
                deps.catalog,
                deps.manifest,
                ingested_doc_ids={c.doc_id for c in retrieved},
            )
        except Exception as exc:  # ranking failure fails the run
            result.tool_calls_made += 1
            trace.tool_calls.append(
                ToolCallRecord(
                    name="rank_adaptation_options", ok=False,
                    duration_ms=(time.monotonic() - started_mono) * 1000,
                    error_code="ranking-error",
                )
            )
            _record_stage(
                trace, "ranking", "failed", started_at, started_mono,
                detail=str(exc)[:300], error_code="ranking-error",
            )
            result.problems.append(f"[ranking-error] Ranking failed: {exc}")
            raise _Abort("ranking-error") from exc
        result.tool_calls_made += 1
        result.ranking = ranking
        trace.tool_calls.append(
            ToolCallRecord(
                name="rank_adaptation_options", ok=True,
                duration_ms=(time.monotonic() - started_mono) * 1000,
                output_summary=summarize(
                    f"ranked={[o.intervention_id for o in ranking.ranked]} "
                    f"excluded={[o.intervention_id for o in ranking.excluded]}"
                ),
            )
        )
        _record_stage(trace, "ranking", "ok", started_at, started_mono)

        # 5. draft (the single LLM call).
        check_bounds("draft")
        started_at = _now()
        started_mono = time.monotonic()
        if result.llm_calls >= config.max_llm_calls:
            raise _Abort("max-llm-calls", "LLM call budget exhausted.")
        registry = build_registry(bundle, ranking)
        citations: list[str] = []
        kept: list[Chunk] = []
        assert deps.manifest is not None
        for chunk in retrieved:
            try:
                citations.append(
                    build_citation(chunk, deps.manifest.get(chunk.doc_id)).formatted
                )
                kept.append(chunk)
            except (KeyError, ValueError) as exc:
                result.warnings.append(
                    f"[citation-drop] {chunk.chunk_id} not citable: {exc}"
                )
        retrieved = kept
        request = build_report_request(
            bundle_json=bundle.model_dump_json(indent=1),
            ranking_json=ranking.model_dump_json(indent=1),
            evidence_block=format_evidence_block(retrieved, citations),
            generator_label=provider.label,
            max_tokens=config.max_tokens,
        ).model_copy(update={"temperature": config.temperature})
        try:
            response = provider.complete(request)
        except LLMError as exc:
            code = _provider_code(exc)
            _record_stage(
                trace, "draft", "failed", started_at, started_mono, error_code=code
            )
            result.problems.append(f"[{code}] Draft call failed: {exc}")
            raise _Abort(code) from exc
        result.llm_calls += 1
        if response.usage is not None:
            result.prompt_tokens += response.usage.prompt_tokens or 0
            result.completion_tokens += response.usage.completion_tokens or 0
        else:
            result.warnings.append("[usage-missing] Provider returned no usage.")
        trace.usage = {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "llm_calls": result.llm_calls,
        }
        if result.prompt_tokens + result.completion_tokens > config.token_budget:
            _record_stage(
                trace, "draft", "failed", started_at, started_mono,
                error_code="token-budget",
            )
            result.problems.append(
                f"[token-budget] Usage {result.prompt_tokens + result.completion_tokens} "
                f"exceeds budget {config.token_budget}; draft discarded."
            )
            raise _Abort("token-budget")
        _record_stage(
            trace, "draft", "ok", started_at, started_mono,
            detail=f"finish={response.finish_reason} "
            f"prompt={result.prompt_tokens} completion={result.completion_tokens}",
        )

        # 6. validate.
        check_bounds("validate")
        started_at = _now()
        started_mono = time.monotonic()
        check_tool_budget()
        try:
            draft = parse_model_json(response.content, response.finish_reason)
        except ValueError as exc:
            result.tool_calls_made += 1
            trace.tool_calls.append(
                ToolCallRecord(
                    name="validate_report", ok=True,
                    duration_ms=(time.monotonic() - started_mono) * 1000,
                    output_summary="verdict=rejected(parse)",
                )
            )
            _record_stage(
                trace, "validate", "ok", started_at, started_mono,
                detail="Draft rejected: unparsable.",
            )
            trace.validator_verdicts.append(str(exc).split("]")[0] + "]")
            result.problems.append(str(exc))
            raise _Abort("draft-rejected") from exc
        verdict = validate_report_tool(
            draft,
            ValidationContext(
                registry=registry,
                chunks={c.chunk_id: c for c in retrieved},
                manifest=deps.manifest,
                pages_by_doc={
                    doc_id: pages
                    for doc_id, pages in deps.pages_by_doc.items()
                    if doc_id in {c.doc_id for c in retrieved}
                },
            ),
        )
        result.tool_calls_made += 1
        if not verdict.valid or verdict.report is None:
            trace.tool_calls.append(
                ToolCallRecord(
                    name="validate_report", ok=True,
                    duration_ms=(time.monotonic() - started_mono) * 1000,
                    output_summary="verdict=rejected("
                    + ",".join(sorted({p[1:].split("]", 1)[0] for p in verdict.problems}))
                    + ")",
                )
            )
            _record_stage(
                trace, "validate", "ok", started_at, started_mono,
                detail=f"Draft rejected ({len(verdict.problems)} problems).",
            )
            trace.validator_verdicts.extend(verdict.problems)
            result.problems.extend(verdict.problems)
            raise _Abort("draft-rejected")
        trace.tool_calls.append(
            ToolCallRecord(
                name="validate_report", ok=True,
                duration_ms=(time.monotonic() - started_mono) * 1000,
                output_summary="verdict=accepted",
            )
        )
        _record_stage(trace, "validate", "ok", started_at, started_mono,
                      detail="Draft accepted.")
        trace.validator_verdicts.append("[accepted]")

        # 7a. finalize an accepted draft.
        check_bounds("finalize")
        started_at = _now()
        started_mono = time.monotonic()
        result.report = verdict.report
        result.status = "complete"
        _record_stage(trace, "finalize", "ok", started_at, started_mono)
    except _Abort as abort:
        # 7b. finalize from whatever deterministic outputs exist.
        code = abort.code
        # Deterministic completion: ranking may still run in finalize when the
        # bundle exists (bounded, offline, no LLM) so the fallback is grounded.
        if bundle is not None and ranking is None and code != "ranking-error":
            started_at = _now()
            started_mono = time.monotonic()
            try:
                assert parsed is not None
                assert deps.manifest is not None and deps.catalog is not None
                ranking = rank_adaptation_options(
                    RankingToolParams(
                        crop=parsed.crop,
                        has_water_source=parsed.has_water_source,
                        has_irrigation_equipment=parsed.has_irrigation_equipment,
                        production_system=parsed.production_system,
                        season=parsed.season,
                        latitude=parsed.latitude,
                        longitude=parsed.longitude,
                    ),
                    bundle,
                    deps.catalog,
                    deps.manifest,
                    ingested_doc_ids={c.doc_id for c in retrieved},
                )
                result.tool_calls_made += 1
                result.ranking = ranking
                trace.tool_calls.append(
                    ToolCallRecord(
                        name="rank_adaptation_options", ok=True,
                        duration_ms=(time.monotonic() - started_mono) * 1000,
                        output_summary="verdict=finalize-completion",
                    )
                )
            except Exception as exc:  # finalize ranking is fatal
                result.problems.append(f"[ranking-error] Finalize ranking failed: {exc}")
                ranking = None
        if bundle is None or ranking is None:
            # No grounded report is possible; the recorded problems explain why.
            if code not in (
                "invalid-scenario", "missing-deps", "bundle-error",
                "ranking-error", "loop-detected",
            ) and not any(p.startswith(f"[{code}]") for p in result.problems):
                result.problems.append(f"[{code}] Run aborted.")
            result.status = "failed"
            result.report = None
        else:
            if not any(p.startswith(f"[{code}]") for p in result.problems):
                result.problems.append(f"[{code}] Fell back to deterministic report.")
            try:
                assert deps.manifest is not None
                result.report = build_fallback_report(
                    bundle, ranking, retrieved, deps.manifest, result.problems
                )
                result.status = "partial"
            except Exception as exc:  # fallback build is fatal
                result.problems.append(f"[fallback-error] Fallback failed: {exc}")
                result.status = "failed"
                result.report = None
        ledger.add("finalize")
        _record_stage(
            trace, "finalize",
            "ok" if result.status == "partial" else "failed",
            _now(), time.monotonic(), detail=f"outcome={result.status}",
        )

    for skipped in STAGES:
        if skipped not in ledger:
            trace.stages.append(
                StageRecord(
                    name=skipped, status="skipped", started_at=_now(), duration_ms=0.0
                )
            )
    trace.ended_at = _now()
    trace.duration_ms_total = (time.monotonic() - t0) * 1000
    trace.outcome = result.status
    trace.problems = list(result.problems)
    trace.warnings = list(result.warnings)
    return result
