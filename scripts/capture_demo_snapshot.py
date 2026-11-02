"""Capture one demo snapshot: a stored real-data run for offline demos.

Default mode runs the fixed agent pipeline with REAL data clients (warm
caches plus live CHIRPS range reads / CDS downloads unless --offline) and the
deterministic no-LLM provider, then stores the full scenario detail as a demo
snapshot. Those snapshots are always deterministic-fallback reports (zero
model calls, zero cost).

``--from-run`` mode (P25) instead builds a snapshot from a saved accepted
agent run file (``data/agent_runs/<run>.json`` plus its ``-trace.json``):
the accepted model report (with per-statement origins), the validator
verdict, and the per-stage trace are preserved verbatim, while the
deterministic bundle/ranking are recomputed locally ($0, no new model call)
and the saved report is re-validated against them before anything is
written. Raw ``draft_text``/``repair_text`` are stripped. The UI labels every
snapshot "cached real-data snapshot" with the timestamp.

Default output is the TRACKED demo/snapshots/ (audit before committing: no
passage text, no secrets, no local paths — see demo/README.md); use --out-dir
for private captures under git-ignored data/ instead.

PowerShell (reference point):

    uv run python scripts/capture_demo_snapshot.py --key reference-morocco `
        --label "Reference: Souss-Massa, Morocco (30.43, -9.61)" `
        --lat 30.43 --lon -9.61

PowerShell (accepted run, $0, no new model call):

    uv run python scripts/capture_demo_snapshot.py --from-run `
        data/agent_runs/run-20261102T202227Z.json `
        --key reference-morocco-ai --label "Reference + Muse Spark (accepted)" `
        --offline --out-dir data/demo_tmp
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from climateadapt.agent.schemas import AgentConfig, AgentDeps, AgentScenario
from climateadapt.agent.tools import (
    BundleToolParams,
    RankingToolParams,
    RetrievalToolParams,
    get_environmental_bundle,
    rank_adaptation_options,
    retrieve_evidence,
)
from climateadapt.agent.trace import RunTrace
from climateadapt.api.demo import (
    DemoSnapshotFile,
    audit_demo_snapshot,
    snapshots_dir,
    write_demo_snapshot,
)
from climateadapt.api.dependencies import UnavailableProvider
from climateadapt.api.scenarios import run_scenario_job, to_detail
from climateadapt.api.schemas_scenarios import ScenarioDetail
from climateadapt.api.store import SqliteScenarioStore
from climateadapt.config import Settings, get_settings
from climateadapt.data.chirps import build_chirps_client
from climateadapt.data.era5_land import build_era5_land_client
from climateadapt.llm.report import Report, build_registry
from climateadapt.llm.validator import ValidationContext, validate_report
from climateadapt.rag.ingest import load_chunks, load_pages, processed_doc_ids
from climateadapt.rag.manifest import load_manifest
from climateadapt.recommend.loader import load_catalog
from climateadapt.schemas_era5 import ALL_BUNDLE_INDICATORS

MANIFEST = Path("corpus/manifest.json")

ACCEPTED_STAMPS = frozenset({"ai-accepted", "ai-partial"})
"""Report acceptances that --from-run will snapshot (never fallback)."""


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_detail_from_run(
    run_data: dict[str, Any],
    trace_data: dict[str, Any],
    *,
    bundle: Any,
    ranking: Any,
    validation_context: ValidationContext,
    scenario_id: str,
    job_id: str = "job-capture",
) -> ScenarioDetail:
    """Assemble a snapshot detail from a saved accepted run (no I/O, no LLM).

    Validates the saved report (accepted stamp, zero problems, fallback off),
    the saved trace (complete outcome, usage, per-stage records, verdicts),
    and re-validates the report against the recomputed deterministic
    registry. Strips raw ``draft_text``/``repair_text``. Raises ValueError on
    any mismatch; callers must fail closed (write nothing).
    """
    if run_data.get("status") != "complete":
        raise ValueError(f"run status is {run_data.get('status')!r}, not 'complete'")
    if run_data.get("problems"):
        raise ValueError(f"run has {len(run_data['problems'])} problems, not zero")
    raw_report = run_data.get("report")
    if not raw_report:
        raise ValueError("run file holds no report")
    report = Report.model_validate(raw_report)
    if report.fallback:
        raise ValueError("run report is a fallback, not an accepted model report")
    if report.acceptance not in ACCEPTED_STAMPS:
        raise ValueError(f"run acceptance is {report.acceptance!r}, not ai-accepted/ai-partial")
    if not report.statement_origins:
        raise ValueError("run report carries no per-statement origins")
    trace = RunTrace.model_validate(trace_data)
    if trace.outcome != "complete":
        raise ValueError(f"trace outcome is {trace.outcome!r}, not 'complete'")
    usage = trace.usage or {}
    if not usage.get("llm_calls"):
        raise ValueError("trace records no LLM calls")
    if not trace.validator_verdicts:
        raise ValueError("trace records no validator verdicts")
    if not trace.stages:
        raise ValueError("trace records no stages")
    scenario = AgentScenario.model_validate(trace.scenario)
    bundle_lat = float(bundle.latitude) if hasattr(bundle, "latitude") else bundle["latitude"]
    bundle_lon = float(bundle.longitude) if hasattr(bundle, "longitude") else bundle["longitude"]
    if bundle_lat != scenario.latitude or bundle_lon != scenario.longitude:
        raise ValueError("recomputed bundle location does not match the saved run")
    recheck = validate_report(report.model_dump(mode="json"), validation_context)
    if not recheck.valid:
        joined = "; ".join(recheck.problems[:4])
        raise ValueError(f"saved report fails re-validation: {joined}")
    trace.draft_text = ""
    trace.repair_text = ""
    try:
        created_at = datetime.fromisoformat(trace.started_at)
        updated_at = (
            datetime.fromisoformat(trace.ended_at) if trace.ended_at else created_at
        )
    except ValueError as exc:
        raise ValueError(f"trace timestamps do not parse: {exc}") from exc
    return ScenarioDetail.model_validate(
        {
            "scenario_id": scenario_id,
            "job_id": job_id,
            "status": "complete",
            "created_at": created_at,
            "updated_at": updated_at,
            "scenario": scenario.model_dump(mode="json"),
            "bundle": bundle.model_dump(mode="json")
            if hasattr(bundle, "model_dump")
            else bundle,
            "ranking": ranking.model_dump(mode="json")
            if hasattr(ranking, "model_dump")
            else ranking,
            "report": report.model_dump(mode="json"),
            "trace": trace.model_dump(mode="json"),
            "problems": [],
            "warnings": list(run_data.get("warnings") or []),
        }
    )


def _build_deps(settings: Settings, chunks: list, manifest: Any, processed_dir: Path) -> AgentDeps:
    return AgentDeps(
        chirps=build_chirps_client(settings),
        era5=build_era5_land_client(settings),
        chunks=chunks,
        manifest=manifest,
        pages_by_doc={
            doc_id: load_pages(processed_dir, doc_id)
            for doc_id in processed_doc_ids(processed_dir)
        },
        catalog=load_catalog(),
    )


def capture_from_run(
    *,
    run_path: Path,
    trace_path: Path,
    key: str,
    label: str,
    out_dir: Path | None,
    settings: Settings,
) -> int:
    """Build a snapshot from a saved accepted run. Returns a process exit code."""
    if not run_path.exists():
        print(f"NOT RUN: run file is missing: {run_path}")
        return 2
    if not trace_path.exists():
        print(f"NOT RUN: trace file is missing: {trace_path} (pass --trace-file)")
        return 2
    if not MANIFEST.exists():
        print("NOT RUN: corpus/manifest.json is missing.")
        return 2
    processed_dir = settings.data_dir / "corpus" / "processed"
    chunks = load_chunks(processed_dir) if processed_dir.exists() else []
    if not chunks:
        print(f"NOT RUN: no ingested corpus at {processed_dir}.")
        return 2
    run_data = _load_json(run_path)
    trace_data = _load_json(trace_path)
    try:
        scenario = AgentScenario.model_validate(trace_data.get("scenario") or {})
    except ValueError as exc:
        print(f"NOT RUN: saved trace scenario is invalid: {exc}")
        return 2
    manifest = load_manifest(MANIFEST)
    deps = _build_deps(settings, chunks, manifest, processed_dir)
    assert deps.chirps is not None and deps.era5 is not None
    assert deps.catalog is not None
    try:
        bundle = get_environmental_bundle(
            BundleToolParams(
                latitude=scenario.latitude,
                longitude=scenario.longitude,
                target_end_month=scenario.target_end_month,
                timescale_months=scenario.timescale_months,
                reference_start_year=scenario.reference_start_year,
                reference_end_year=scenario.reference_end_year,
                min_reference_years=scenario.min_reference_years,
                land_fallback_max_km=scenario.land_fallback_max_km,
                indicators=list(scenario.indicators),
            ),
            deps.chirps,
            deps.era5,
        )
        retrieval = retrieve_evidence(
            RetrievalToolParams(
                query=scenario.query,
                top_k=scenario.top_k,
                exclude_reference=scenario.exclude_reference,
            ),
            deps.chunks,
            deps.dense_retriever,
        )
        retrieved = [hit.chunk for hit in retrieval.hits]
        ranking = rank_adaptation_options(
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
            manifest,
            ingested_doc_ids={c.doc_id for c in retrieved},
        )
    except Exception as exc:
        print(f"NOT RUN: deterministic recompute failed: {exc}")
        return 1
    finally:
        try:
            deps.chirps.store.close()
        except Exception:  # best-effort
            pass
    wanted = {c.doc_id for c in retrieved}
    ctx = ValidationContext(
        registry=build_registry(bundle, ranking),
        chunks={c.chunk_id: c for c in retrieved},
        manifest=manifest,
        pages_by_doc={
            doc_id: pages
            for doc_id, pages in deps.pages_by_doc.items()
            if doc_id in wanted
        },
    )
    try:
        detail = build_detail_from_run(
            run_data,
            trace_data,
            bundle=bundle,
            ranking=ranking,
            validation_context=ctx,
            scenario_id=f"capture-{key}",
        )
    except ValueError as exc:
        print(f"NOT WRITTEN: {exc}")
        return 1
    captured_at = datetime.now(UTC)
    candidate = DemoSnapshotFile(
        key=key, label=label, captured_at_utc=captured_at, detail=detail
    )
    audit_problems = audit_demo_snapshot(candidate)
    if audit_problems:
        print("NOT WRITTEN: snapshot audit failed (fail closed):")
        for problem in audit_problems[:12]:
            print(f"  audit: {problem}")
        return 1
    assert detail.report is not None and detail.trace is not None
    usage = detail.trace.usage or {}
    origins = detail.report.statement_origins
    model_count = sum(1 for origin in origins.values() if origin == "model")
    print(f"outcome: complete (accepted {detail.report.acceptance})")
    print(f"  report generator={detail.report.generator} fallback=False")
    print(f"  statements: {model_count}/{len(origins)} model-written (validated)")
    print(
        f"  llm_calls={usage.get('llm_calls')} "
        f"prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')}"
    )
    print(f"  duration_ms_total={detail.trace.duration_ms_total:.0f}")
    for stage in detail.trace.stages:
        print(f"  stage {stage.name}: {stage.status} {stage.duration_ms:.0f} ms")
    for verdict in detail.trace.validator_verdicts[:4]:
        print(f"  verdict: {verdict[:200]}")
    for warning in detail.warnings[:6]:
        print(f"  warning: {warning[:160]}")
    directory = snapshots_dir(settings.data_dir, out_dir)
    path = write_demo_snapshot(directory, key, label, captured_at, detail)
    print(f"saved: {path} ({path.stat().st_size} bytes)")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lon", type=float, default=None)
    parser.add_argument("--key", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--target-end", default="2024-03")
    parser.add_argument("--timescale", type=int, default=3)
    parser.add_argument("--query", default="deficit irrigation scheduling")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force cache-only clients (no downloads, no CDS requests).",
    )
    parser.add_argument("--out-dir", default=None)
    parser.add_argument(
        "--from-run",
        default=None,
        help="Build from a saved agent run file (data/agent_runs/<run>.json).",
    )
    parser.add_argument(
        "--trace-file",
        default=None,
        help="Trace JSON for --from-run (defaults to <run-stem>-trace.json).",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.offline:
        settings = settings.model_copy(update={"allow_downloads": False})

    if args.from_run:
        run_path = Path(args.from_run)
        if args.trace_file:
            trace_path = Path(args.trace_file)
        else:
            trace_path = run_path.parent / f"{run_path.stem}-trace.json"
        out_dir = Path(args.out_dir) if args.out_dir else None
        return capture_from_run(
            run_path=run_path,
            trace_path=trace_path,
            key=args.key,
            label=args.label,
            out_dir=out_dir,
            settings=settings,
        )

    if args.lat is None or args.lon is None:
        print("NOT RUN: --lat and --lon are required without --from-run.")
        return 2
    if not MANIFEST.exists():
        print("NOT RUN: corpus/manifest.json is missing.")
        return 2
    processed_dir = settings.data_dir / "corpus" / "processed"
    chunks = load_chunks(processed_dir) if processed_dir.exists() else []
    if not chunks:
        print(f"NOT RUN: no ingested corpus at {processed_dir}.")
        return 2

    scenario = AgentScenario.model_validate(
        {
            "latitude": args.lat,
            "longitude": args.lon,
            "target_end_month": args.target_end,
            "timescale_months": args.timescale,
            "reference_start_year": 1991,
            "reference_end_year": 2020,
            "min_reference_years": 30,
            "land_fallback_max_km": 15.0,
            "indicators": list(ALL_BUNDLE_INDICATORS),
            "query": args.query,
            "top_k": args.top_k,
            "exclude_reference": True,
            "crop": "wheat",
            "has_water_source": True,
            "has_irrigation_equipment": True,
            "production_system": "irrigated",
            "season": args.target_end,
        }
    )
    deps = AgentDeps(
        chirps=build_chirps_client(settings),
        era5=build_era5_land_client(settings),
        chunks=chunks,
        manifest=load_manifest(MANIFEST),
        pages_by_doc={
            doc_id: load_pages(processed_dir, doc_id)
            for doc_id in processed_doc_ids(processed_dir)
        },
        catalog=load_catalog(),
    )
    db_path = settings.data_dir / "capture-tmp.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        leftover = db_path.parent / f"{db_path.name}{suffix}"
        if leftover.exists():
            leftover.unlink()
    store = SqliteScenarioStore(db_path)
    scenario_id = f"capture-{args.key}"
    store.create(scenario_id, "job-capture", scenario.model_dump(mode="json"))
    print("provider: unavailable (deterministic snapshot, zero model calls)")
    job = run_scenario_job(
        scenario_id,
        store=store,
        deps=deps,
        provider=UnavailableProvider(),
        config=AgentConfig(total_timeout_seconds=args.timeout),
    )
    outcome = job(lambda done, total: None)
    row = store.get(scenario_id)
    store.close()
    for suffix in ("", "-wal", "-shm"):
        leftover = db_path.parent / f"{db_path.name}{suffix}"
        if leftover.exists():
            leftover.unlink()
    try:
        deps.chirps.store.close()
    except Exception:  # best-effort
        pass
    if row is None:
        print("FAILED: scenario row vanished mid-run.")
        return 1
    detail = to_detail(row)
    print(f"outcome: {outcome}")
    for entry in (detail.bundle.entries if detail.bundle else []):
        print(f"  entry {entry.indicator}: {entry.status} err={entry.error_type}")
    if detail.ranking:
        print(
            f"  ranked {[o.intervention_id for o in detail.ranking.ranked]}, "
            f"excluded {[o.intervention_id for o in detail.ranking.excluded]}"
        )
    if detail.report:
        print(
            f"  report fallback={detail.report.fallback} "
            f"generator={detail.report.generator}"
        )
    for problem in detail.problems[:6]:
        print(f"  problem: {problem[:160]}")
    for warning in detail.warnings[:6]:
        print(f"  warning: {warning[:160]}")

    out_dir = Path(args.out_dir) if args.out_dir else None
    directory = snapshots_dir(settings.data_dir, out_dir)
    path = write_demo_snapshot(
        directory,
        args.key,
        args.label,
        datetime.now(UTC),
        detail,
    )
    print(f"saved: {path} ({path.stat().st_size} bytes)")
    return 0 if detail.status in ("complete", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
