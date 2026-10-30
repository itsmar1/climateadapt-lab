"""Extract text, chunk, and store the PDFs found under data/corpus/raw/.

    uv run python scripts/corpus_ingest.py
    uv run python scripts/corpus_ingest.py --chunk-words 180 --overlap-words 30
    uv run python scripts/corpus_ingest.py --max-page-span 2

Outputs data/corpus/processed/<doc_id>/{pages.jsonl,chunks.jsonl,meta.json}. Chunks dropped as
too short or mostly non-letters (tables) are counted and reported, never silently lost.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.rag.chunking import ChunkingParams
from climateadapt.rag.ingest import (
    IngestError,
    ingest_document,
    load_chunks,
    load_pages,
    processed_doc_ids,
)
from climateadapt.rag.manifest import load_manifest

MANIFEST = Path("corpus/manifest.json")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="limit to these doc_ids")
    parser.add_argument("--chunk-words", type=int, default=ChunkingParams.chunk_words)
    parser.add_argument("--overlap-words", type=int, default=ChunkingParams.overlap_words)
    parser.add_argument("--max-page-span", type=int, default=None,
                        help="cut chunks spanning more pages (default: no cap)")
    args = parser.parse_args()

    params = ChunkingParams(chunk_words=args.chunk_words, overlap_words=args.overlap_words,
                            max_page_span=args.max_page_span)
    settings = get_settings()
    raw_dir = settings.data_dir / "corpus" / "raw"
    processed_dir = settings.data_dir / "corpus" / "processed"
    manifest = load_manifest(MANIFEST)

    print(f"{'doc_id':<58}{'pages':>6}{'empty':>6}{'words':>9}{'chunks':>8}"
          f"{'drop s/a':>10}{'refs':>6}")
    errors = 0
    for doc in manifest.documents:
        if args.only and doc.doc_id not in args.only:
            continue
        try:
            report = ingest_document(
                doc, raw_dir=raw_dir, processed_dir=processed_dir, params=params
            )
        except IngestError as exc:
            errors += 1
            print(f"{doc.doc_id:<58}  SKIPPED: {exc}")
            continue
        print(
            f"{doc.doc_id:<58}{report.n_pages:>6}{len(report.empty_pages):>6}"
            f"{report.n_words:>9}{report.n_chunks:>8}"
            f"{report.n_dropped_short:>5}/{report.n_dropped_low_alpha:<4}"
            f"{report.n_reference_chunks:>6}"
        )
        for warning in report.warnings:
            print(f"    WARNING: {warning}")
    selected = {d.doc_id for d in manifest.documents if not args.only or d.doc_id in args.only}
    have = sorted(processed_doc_ids(processed_dir) & selected)
    spans: dict[int, int] = {}
    n_chunks = n_ref = n_pages = labeled = 0
    for doc_id in have:
        for chunk in load_chunks(processed_dir, [doc_id]):
            n_chunks += 1
            if chunk.section_type == "references":
                n_ref += 1
            span = chunk.page_end - chunk.page_start + 1
            spans[span] = spans.get(span, 0) + 1
        for page in load_pages(processed_dir, doc_id):
            n_pages += 1
            if page.label is not None:
                labeled += 1
    if n_chunks:
        dist = " ".join(f"{s}:{spans[s]}" for s in sorted(spans))
        print(f"\npage-span distribution over {n_chunks} chunks (span:count): {dist}")
        print(f"reference chunks: {n_ref}; pages with printed labels: {labeled}/{n_pages}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())