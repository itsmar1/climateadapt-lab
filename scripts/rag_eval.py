"""Evaluate retrieval on the gold set in corpus/eval/queries.json.

    uv run python scripts/rag_eval.py
    uv run python scripts/rag_eval.py --misses 3
    uv run python scripts/rag_eval.py --retriever dense
    uv run python scripts/rag_eval.py --compare
    uv run python scripts/rag_eval.py --k-sweep

Labels are document-level and were written by the assistant from verified abstracts, not from
page text: review them. Queries whose relevant documents are not ingested are skipped and listed.
Dense and hybrid arms need a built index (run scripts/rag_index.py first); comparisons on
~10 evaluable queries are exploratory, not statistically reliable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.rag.dense import (
    DenseRetriever,
    QdrantStore,
    StaleIndexError,
    collection_name,
    default_fingerprint_path,
    uniform_chunk_params,
)
from climateadapt.rag.embeddings import E5_SMALL_MODEL_ID, E5Embedder
from climateadapt.rag.evaluation import Aggregate, EvalReport, evaluate, load_eval_set
from climateadapt.rag.fusion import DEFAULT_RRF_K
from climateadapt.rag.ingest import load_chunks, processed_doc_ids
from climateadapt.rag.manifest import load_manifest
from climateadapt.rag.retrieval import Bm25Retriever, HybridRetriever, Retriever

MANIFEST = Path("corpus/manifest.json")
EVAL_SET = Path("corpus/eval/queries.json")
K_SWEEP = (10, 30, 60, 100)


def _row(label: str, agg: Aggregate, ks: list[int]) -> str:
    hits = " ".join(f"{agg.hit_rate_at[k]:5.2f}" for k in ks)
    recalls = " ".join(f"{agg.doc_recall_at[k]:5.2f}" for k in ks)
    return f"{label:<10}{agg.n_queries:>4}   {hits}   |  {recalls}   |  {agg.mrr:5.2f}"


def _summary(label: str, report: EvalReport) -> str:
    o = report.overall
    return (
        f"{label:<16}n={o.n_queries:>2}   "
        f"hit@1={o.hit_rate_at[1]:.2f} hit@10={o.hit_rate_at[10]:.2f}   "
        f"MRR={o.mrr:.2f}"
    )


def _print_report(title: str, report: EvalReport, misses: int) -> None:
    ks = report.ks
    print(f"\n== {title} ==")
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

    print(f"\nqueries without a relevant document in the top {misses}:")
    shown = 0
    for outcome in report.outcomes:
        if outcome.first_relevant_rank is None or outcome.first_relevant_rank > misses:
            shown += 1
            top = ", ".join(
                f"{r.doc_id.split('-')[0]}:{r.doc_id[:28]}"
                for r in outcome.retrieved[:3]
            )
            print(f"  {outcome.query_id} [{outcome.language}] first relevant rank: "
                  f"{outcome.first_relevant_rank}   top results: {top or 'none'}")
    if not shown:
        print("  none")


def _open_dense(chunks, processed_dir, qdrant_dir, device) -> tuple[DenseRetriever, QdrantStore]:
    """Open the persisted dense index (never builds; rag_index.py builds)."""
    params = uniform_chunk_params(processed_dir, sorted(processed_doc_ids(processed_dir)))
    embedder = E5Embedder(model_id=E5_SMALL_MODEL_ID, device=device)
    store = QdrantStore(qdrant_dir)
    fingerprint_path = default_fingerprint_path(
        qdrant_dir, collection_name(embedder.model_id, embedder.dim, params)
    )
    retriever = DenseRetriever(
        chunks,
        embedder=embedder,
        store=store,
        params=params,
        fingerprint_path=fingerprint_path,
        build=False,
    )
    return retriever, store


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--misses", type=int, default=3, help="show queries missing in top N")
    parser.add_argument("--retriever", choices=["bm25", "dense", "hybrid"], default="bm25")
    parser.add_argument("--compare", action="store_true", help="run bm25, dense, hybrid")
    parser.add_argument("--rrf-k", type=int, default=DEFAULT_RRF_K, help="RRF k for hybrid")
    parser.add_argument("--k-sweep", action="store_true", help="hybrid at k=10,30,60,100")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--qdrant-dir", default=None)
    args = parser.parse_args()

    manifest = load_manifest(MANIFEST)
    eval_set = load_eval_set(EVAL_SET, manifest)
    processed_dir = get_settings().data_dir / "corpus" / "processed"
    available = processed_doc_ids(processed_dir)
    if not available:
        print("No ingested documents. Run scripts/corpus_fetch.py and scripts/corpus_ingest.py.")
        return 2
    chunks = load_chunks(processed_dir)
    qdrant_dir = Path(args.qdrant_dir) if args.qdrant_dir else get_settings().data_dir / "qdrant"

    closers: list[QdrantStore] = []
    shared: dict[str, Retriever] = {}

    def build(name: str, rrf_k: int) -> Retriever:
        if name == "bm25":
            return Bm25Retriever(chunks)
        if "dense" not in shared:
            dense, store = _open_dense(chunks, processed_dir, qdrant_dir, args.device)
            closers.append(store)
            shared["dense"] = dense
        if name == "dense":
            return shared["dense"]
        return HybridRetriever([Bm25Retriever(chunks), shared["dense"]], rrf_k=rrf_k)

    try:
        if args.k_sweep:
            print("RRF k sweep (hybrid bm25+dense; exploratory: ~10 queries):")
            for k in K_SWEEP:
                report = evaluate(build("hybrid", k), eval_set, available)
                print(f"  k={k:<4}" + _summary("hybrid", report)[16:])
            print("Small-n caveat: k differences on ~10 queries are noise-prone; "
                  f"default stays k={DEFAULT_RRF_K} unless numbers clearly justify a change.")
            return 0
        arms = (
            [("bm25", args.rrf_k), ("dense", args.rrf_k), ("hybrid", args.rrf_k)]
            if args.compare
            else [(args.retriever, args.rrf_k)]
        )
        reports: list[tuple[str, EvalReport]] = []
        for name, k in arms:
            label = name if name != "hybrid" else f"hybrid(k={k})"
            reports.append((label, evaluate(build(name, k), eval_set, available)))
        for label, report in reports:
            _print_report(label, report, args.misses)
        if args.compare:
            print("\nsummary (overall):")
            for label, report in reports:
                print("  " + _summary(label, report))
    except StaleIndexError as exc:
        print(exc)
        return 2
    finally:
        for store in closers:
            store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
