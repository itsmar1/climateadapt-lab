"""One gated live report: warm-cache bundle + BM25 evidence + a single Baseten call.

Runs ONLY when CLIMATEADAPT_RUN_LIVE_LLM=1 and a Baseten API key is configured.
Makes exactly ONE model call: the environmental bundle comes from local caches
(downloads forced off), retrieval is offline BM25, ranking is deterministic.
The draft is validated client-side; anything invalid yields the labelled
deterministic fallback. Prints latency, token usage, the verdict, and the
saved report path; never prints the API key.

PowerShell, current session only:

    $env:CLIMATEADAPT_RUN_LIVE_LLM = "1"
    uv run python scripts/llm_report.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from climateadapt.api.bundle import run_environmental_bundle
from climateadapt.config import get_settings
from climateadapt.data.chirps import build_chirps_client
from climateadapt.data.era5_land import build_era5_land_client
from climateadapt.data.periods import YearMonth
from climateadapt.llm.fallback import build_fallback_report
from climateadapt.llm.prompts import build_report_request, format_evidence_block
from climateadapt.llm.provider import BasetenProvider
from climateadapt.llm.report import build_registry
from climateadapt.llm.service import generate_report
from climateadapt.llm.validator import ValidationContext
from climateadapt.rag.citations import build_citation
from climateadapt.rag.ingest import load_chunks, load_pages
from climateadapt.rag.manifest import load_manifest
from climateadapt.rag.retrieval import Bm25Retriever
from climateadapt.recommend.loader import load_catalog
from climateadapt.recommend.schema import ScenarioContext
from climateadapt.recommend.service import recommend
from climateadapt.schemas_era5 import ALL_BUNDLE_INDICATORS, EnvironmentalBundleResponse

GATE_ENV_VAR = "CLIMATEADAPT_RUN_LIVE_LLM"
MANIFEST = Path("corpus/manifest.json")

# Reference scenario (same point/window as the P05 live bundle check).
LATITUDE = 30.43
LONGITUDE = -9.61
TARGET_END_MONTH = YearMonth(2024, 3)
TIMESCALE_MONTHS = 3
REFERENCE_START_YEAR = 1991
REFERENCE_END_YEAR = 2020
MIN_REFERENCE_YEARS = 30
LAND_FALLBACK_MAX_KM = 15.0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--query", default="deficit irrigation scheduling drought adaptation")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=4000)
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

    offline = settings.model_copy(update={"allow_downloads": False})
    chirps = build_chirps_client(offline)
    era5 = build_era5_land_client(offline)
    try:
        bundle_dict = run_environmental_bundle(
            chirps,
            era5,
            latitude=LATITUDE,
            longitude=LONGITUDE,
            target_end_month=TARGET_END_MONTH,
            timescale_months=TIMESCALE_MONTHS,
            reference_start_year=REFERENCE_START_YEAR,
            reference_end_year=REFERENCE_END_YEAR,
            min_reference_years=MIN_REFERENCE_YEARS,
            land_fallback_max_km=LAND_FALLBACK_MAX_KM,
            indicators=list(ALL_BUNDLE_INDICATORS),
        )
    finally:
        try:
            chirps.store.close()
        except Exception:  # best-effort
            pass
    bundle = EnvironmentalBundleResponse.model_validate(bundle_dict)
    statuses = {entry.indicator: entry.status for entry in bundle.entries}
    print(f"bundle statuses: {statuses}")
    if all(status != "ok" for status in statuses.values()):
        print("NOT RUN: no bundle indicator computed from warm caches.")
        return 2

    manifest = load_manifest(MANIFEST)
    chunks = load_chunks(processed_dir)
    if not chunks:
        print("NOT RUN: ingested corpus holds no chunks.")
        return 2
    hits = Bm25Retriever(chunks).search(args.query, args.top_k, exclude_reference=True)
    if not hits:
        print("NOT RUN: retrieval returned no passages.")
        return 2
    retrieved = [hit.chunk for hit in hits]
    print(f"retrieved: {[c.chunk_id for c in retrieved]}")

    catalog = load_catalog()
    scenario = ScenarioContext.model_validate(
        {
            "crop": "wheat",
            "has_water_source": True,
            "has_irrigation_equipment": True,
            "production_system": "irrigated",
            "season": "2024-03",
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
        }
    )
    recommendations = recommend(
        catalog, scenario, bundle, manifest,
        ingested_doc_ids={c.doc_id for c in retrieved},
    )
    print(
        f"ranking: {[o.intervention_id for o in recommendations.ranked]} "
        f"excluded: {[o.intervention_id for o in recommendations.excluded]}"
    )

    registry = build_registry(bundle, recommendations)
    citations = [build_citation(chunk, manifest.get(chunk.doc_id)) for chunk in retrieved]
    evidence_block = format_evidence_block(
        retrieved, [c.formatted for c in citations]
    )
    provider = BasetenProvider()
    request = build_report_request(
        bundle_json=bundle.model_dump_json(indent=1),
        ranking_json=recommendations.model_dump_json(indent=1),
        evidence_block=evidence_block,
        generator_label=provider.label,
        max_tokens=args.max_tokens,
    )
    print(f"model: {provider.model_id}; max_tokens={args.max_tokens}; one call follows")

    pages_by_doc = {
        doc_id: load_pages(processed_dir, doc_id)
        for doc_id in {c.doc_id for c in retrieved}
    }
    ctx = ValidationContext(
        registry=registry,
        chunks={c.chunk_id: c for c in retrieved},
        manifest=manifest,
        pages_by_doc=pages_by_doc,
    )
    try:
        outcome = generate_report(
            provider,
            request,
            ctx,
            lambda problems: build_fallback_report(
                bundle, recommendations, retrieved, manifest, problems
            ),
        )
    finally:
        provider.close()

    print(f"accepted: {outcome.accepted} (fallback={outcome.report.fallback})")
    print(f"latency_ms: {outcome.latency_ms:.0f}; attempts: {outcome.attempts}")
    if outcome.usage is not None:
        print(f"usage: {outcome.usage.model_dump_json()}")
    else:
        print("usage: none returned")
    if outcome.problems:
        print("problems:")
        for problem in outcome.problems[:12]:
            print(f"  {problem[:300]}")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = settings.data_dir / "llm_reports" / f"report-{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "accepted": outcome.accepted,
                "problems": outcome.problems,
                "usage": outcome.usage.model_dump() if outcome.usage else None,
                "latency_ms": outcome.latency_ms,
                "attempts": outcome.attempts,
                "report": outcome.report.model_dump(mode="json"),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
