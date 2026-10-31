"""Gated live end-to-end agent run for the reference scenario.

Runs ONLY when CLIMATEADAPT_RUN_LIVE_LLM=1 and a Baseten API key is configured.
The environmental bundle comes from local caches (downloads forced off),
retrieval is offline BM25, ranking is deterministic, and the pipeline makes at
most ONE model call (AgentConfig.max_llm_calls). Prints the outcome, timings,
token usage, and the saved trace/report path; never prints the API key.

PowerShell, current session only:

    $env:CLIMATEADAPT_RUN_LIVE_LLM = "1"
    uv run python scripts/run_agent.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from climateadapt.agent.schemas import AgentConfig, AgentDeps, AgentScenario
from climateadapt.agent.trace import save_trace
from climateadapt.agent.workflow import run_agent
from climateadapt.config import get_settings
from climateadapt.data.chirps import build_chirps_client
from climateadapt.data.era5_land import build_era5_land_client
from climateadapt.llm.provider import BasetenProvider
from climateadapt.rag.ingest import load_chunks, load_pages, processed_doc_ids
from climateadapt.rag.manifest import load_manifest
from climateadapt.recommend.loader import load_catalog

GATE_ENV_VAR = "CLIMATEADAPT_RUN_LIVE_LLM"
MANIFEST = Path("corpus/manifest.json")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lat", type=float, default=30.43)
    parser.add_argument("--lon", type=float, default=-9.61)
    parser.add_argument("--query", default="deficit irrigation scheduling drought adaptation")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--token-budget", type=int, default=100000)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if os.environ.get(GATE_ENV_VAR) != "1":
        print(f"NOT RUN: {GATE_ENV_VAR}=1 is not set (refusing live LLM calls).")
        return 2
    settings = get_settings()
    secret = settings.baseten_api_key
    if secret is None or not secret.get_secret_value():
        print("NOT RUN: no Baseten API key configured (set CLIMATEADAPT_BASETEN_API_KEY).")
        return 2
    if not MANIFEST.exists():
        print("NOT RUN: corpus/manifest.json is missing.")
        return 2
    processed_dir = settings.data_dir / "corpus" / "processed"
    if not processed_dir.exists():
        print(f"NOT RUN: no ingested corpus at {processed_dir}.")
        return 2

    scenario = AgentScenario.model_validate(
        {
            "latitude": args.lat,
            "longitude": args.lon,
            "target_end_month": "2024-03",
            "timescale_months": 3,
            "reference_start_year": 1991,
            "reference_end_year": 2020,
            "min_reference_years": 30,
            "land_fallback_max_km": 15.0,
            "query": args.query,
            "top_k": args.top_k,
            "crop": "wheat",
            "has_water_source": True,
            "has_irrigation_equipment": True,
            "production_system": "irrigated",
            "season": "2024-03",
        }
    )
    config = AgentConfig.model_validate(
        {
            "token_budget": args.token_budget,
            "total_timeout_seconds": args.timeout,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        }
    )
    print(f"temperature: {config.temperature} (seed: unsupported by model, not set)")
    print(f"max_tokens: {config.max_tokens}; token_budget: {config.token_budget}")

    offline = settings.model_copy(update={"allow_downloads": False})
    chirps = build_chirps_client(offline)
    era5 = build_era5_land_client(offline)
    manifest = load_manifest(MANIFEST)
    chunks = load_chunks(processed_dir)
    if not chunks:
        print("NOT RUN: ingested corpus holds no chunks.")
        return 2
    deps = AgentDeps(
        chirps=chirps,
        era5=era5,
        chunks=chunks,
        manifest=manifest,
        pages_by_doc={
            doc_id: load_pages(processed_dir, doc_id)
            for doc_id in processed_doc_ids(processed_dir)
        },
        catalog=load_catalog(),
    )
    provider = BasetenProvider(timeout_seconds=config.llm_timeout_seconds)
    print(f"model: {provider.model_id}; at most one call follows")
    try:
        result = run_agent(scenario, deps, provider, config)
    finally:
        provider.close()
        try:
            chirps.store.close()
        except Exception:  # best-effort
            pass

    print(f"status: {result.status}")
    print(f"stages: {[(s.name, s.status) for s in result.trace.stages]}")
    print(f"tool_calls: {result.tool_calls_made}; llm_calls: {result.llm_calls}")
    print(f"tokens: prompt={result.prompt_tokens} completion={result.completion_tokens}")
    print(f"total_ms: {result.trace.duration_ms_total:.0f}")
    if result.problems:
        print("problems:")
        for problem in result.problems[:12]:
            print(f"  {problem[:300]}")
    if result.warnings:
        print("warnings:")
        for warning in result.warnings[:8]:
            print(f"  {warning[:300]}")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = settings.data_dir / "agent_runs" / f"run-{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "status": result.status,
                "problems": result.problems,
                "warnings": result.warnings,
                "report": (
                    result.report.model_dump(mode="json") if result.report else None
                ),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    trace_path = save_trace(
        result.trace, out_path.parent / f"{out_path.stem}-trace.json"
    )
    print(f"saved: {out_path}")
    print(f"trace: {trace_path}")
    return 0 if result.status in ("complete", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
