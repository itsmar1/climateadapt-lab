"""Evaluate retrieval on the gold set in corpus/eval/queries.json.

    uv run python scripts/rag_eval.py
    uv run python scripts/rag_eval.py --misses 3

Labels are document-level and were written by the assistant from verified abstracts, not from
page text: review them. Queries whose relevant documents are not ingested are skipped and listed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.rag.evaluation import Aggregate, evaluate, load_eval_set
from climateadapt.rag.ingest import load_chunks, processed_doc_ids
from climateadapt.rag.manifest import load_manifest
from climateadapt.rag.retrieval import Bm25Retriever

MANIFEST = Path("corpus/manifest.json")
EVAL_SET = Path("corpus/eval/queries.json")


def _row(label: str, agg: Aggregate, ks: list[int]) -> str:
    hits = " ".join(f"{agg.hit_rate_at[k]:5.2f}" for k in ks)
    recalls = " ".join(f"{agg.doc_recall_at[k]:5.2f}" for k in ks)
    return f"{label:<10}{agg.n_queries:>4}   {hits}   |  {recalls}   |  {agg.mrr:5.2f}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--misses", type=int, default=3, help="show queries missing in top N")
    args = parser.parse_args()

    manifest = load_manifest(MANIFEST)
    eval_set = load_eval_set(EVAL_SET, manifest)
    processed_dir = get_settings().data_dir / "corpus" / "processed"
    available = processed_doc_ids(processed_dir)
    if not available:
        print("No ingested documents. Run scripts/corpus_fetch.py and scripts/corpus_ingest.py.")
        return 2

    report = evaluate(Bm25Retriever(load_chunks(processed_dir)), eval_set, available)
    ks = report.ks
    print(
        f"retriever: {report.retriever}   evaluated: {report.n_evaluated}   "
        f"skipped: {report.n_skipped}"
    )
    if report.documents_missing:
        print(f"documents not ingested: {', '.join(report.documents_missing)}")
    for query_id, reason in report.skipped.items():
        print(f"  skipped {query_id}: {reason}")
    header = " ".join(f"@{k:<4}" for k in ks)
    print(f"\n{'':<10}{'n':>4}   hit {header}|  doc recall {header}|  MRR")
    print(_row("overall", report.overall, ks))
    for language, aggregate in report.by_language.items():
        print(_row(language, aggregate, ks))

    print(f"\nqueries without a relevant document in the top {args.misses}:")
    shown = 0
    for outcome in report.outcomes:
        if outcome.first_relevant_rank is None or outcome.first_relevant_rank > args.misses:
            shown += 1
            top = ", ".join(
                f"{r.doc_id.split('-')[0]}:{r.doc_id[:28]}"
                for r in outcome.retrieved[:3]
            )
            print(f"  {outcome.query_id} [{outcome.language}] first relevant rank: "
                  f"{outcome.first_relevant_rank}   top results: {top or 'none'}")
    if not shown:
        print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main())