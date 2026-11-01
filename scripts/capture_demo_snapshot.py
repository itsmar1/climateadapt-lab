"""Capture one demo snapshot: a stored real-data run for offline demos.

Runs the fixed agent pipeline with REAL data clients (warm caches plus live
CHIRPS range reads / CDS downloads unless --offline) and the deterministic
no-LLM provider, then stores the full scenario detail as a demo snapshot.
Snapshots are always deterministic-fallback reports (zero model calls, zero
cost); the UI labels them "cached real-data snapshot" with the timestamp.

PowerShell (reference point):

    uv run python scripts/capture_demo_snapshot.py --key reference-morocco `
        --label "Reference: Souss-Massa, Morocco (30.43, -9.61)" `
        --lat 30.43 --lon -9.61
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from climateadapt.agent.schemas import AgentConfig, AgentDeps, AgentScenario
from climateadapt.api.demo import snapshots_dir, write_demo_snapshot
from climateadapt.api.dependencies import UnavailableProvider
from climateadapt.api.scenarios import run_scenario_job, to_detail
from climateadapt.api.store import SqliteScenarioStore
from climateadapt.config import get_settings
from climateadapt.data.chirps import build_chirps_client
from climateadapt.data.era5_land import build_era5_land_client
from climateadapt.rag.ingest import load_chunks, load_pages, processed_doc_ids
from climateadapt.rag.manifest import load_manifest
from climateadapt.recommend.loader import load_catalog
from climateadapt.schemas_era5 import ALL_BUNDLE_INDICATORS

MANIFEST = Path("corpus/manifest.json")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
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
    args = parser.parse_args()

    settings = get_settings()
    if args.offline:
        settings = settings.model_copy(update={"allow_downloads": False})
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
