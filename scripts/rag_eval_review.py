"""Generate data/corpus/eval_review.md: each gold query with its top-3 BM25 hits.

Owner aid for correcting relevant_doc_ids and adding relevant_pages in
corpus/eval/queries.json. Short excerpts only; the review file is git-ignored
(data/corpus/). This script never edits the gold labels.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.rag.citations import build_citation, verify_citation
from climateadapt.rag.evaluation import load_eval_set
from climateadapt.rag.ingest import load_chunks, load_pages
from climateadapt.rag.manifest import load_manifest
from climateadapt.rag.retrieval import Bm25Retriever

MANIFEST = Path("corpus/manifest.json")
EVAL_SET = Path("corpus/eval/queries.json")
EXCERPT_CHARS = 200


def _excerpt(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= EXCERPT_CHARS else collapsed[:EXCERPT_CHARS] + "..."


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exclude-reference", action="store_true",
                        help="drop reference-list chunks from the top-3")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    manifest = load_manifest(MANIFEST)
    eval_set = load_eval_set(EVAL_SET, manifest)
    processed_dir = get_settings().data_dir / "corpus" / "processed"
    chunks = load_chunks(processed_dir)
    if not chunks:
        print("No ingested chunks. Run scripts/corpus_ingest.py first.")
        return 2
    retriever = Bm25Retriever(chunks)
    pages_cache: dict[str, list] = {}

    lines = [
        "# Gold-set review (generated, do not commit)",
        "",
        f"Top-{args.top_k} BM25 hits per query over {len(chunks)} ingested chunks "
        f"(exclude_reference={args.exclude_reference}).",
        "Correct `relevant_doc_ids` / add `relevant_pages` in corpus/eval/queries.json.",
        "",
    ]
    for query in eval_set.queries:
        lines.append(f"## {query.id} [{query.language}]")
        lines.append("")
        lines.append(f"> {query.query}")
        lines.append("")
        lines.append(f"Current labels: relevant_doc_ids={query.relevant_doc_ids} "
                     f"relevant_pages={query.relevant_pages}")
        lines.append("")
        hits = retriever.search(query.query, args.top_k, exclude_reference=args.exclude_reference)
        if not hits:
            lines.append("No hits.")
        for rank, hit in enumerate(hits, start=1):
            chunk = hit.chunk
            try:
                doc = manifest.get(chunk.doc_id)
            except KeyError:
                lines.append(f"{rank}. {chunk.doc_id} (NOT IN MANIFEST)")
                continue
            citation = build_citation(chunk, doc)
            pages = pages_cache.setdefault(chunk.doc_id, load_pages(processed_dir, chunk.doc_id))
            problems = verify_citation(chunk, manifest, {chunk.doc_id: pages})
            verdict = "citation OK" if not problems else f"CITATION PROBLEMS: {problems}"
            lines.append(f"{rank}. {chunk.doc_id} [{chunk.section_type}] "
                             f"{citation.pages} ({verdict})")
            lines.append(f"   {doc.title}")
            lines.append(f"   excerpt: {_excerpt(chunk.text)}")
        lines.append("")
    out = get_settings().data_dir / "corpus" / "eval_review.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({len(eval_set.queries)} queries).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
