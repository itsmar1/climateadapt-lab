"""Search the ingested corpus with BM25 and print results with their citations.

    uv run python scripts/rag_search.py "supplemental irrigation rainfed wheat" --top-k 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.rag.citations import build_citation
from climateadapt.rag.ingest import load_chunks
from climateadapt.rag.manifest import load_manifest
from climateadapt.rag.retrieval import Bm25Retriever

MANIFEST = Path("corpus/manifest.json")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--snippet-chars", type=int, default=350)
    parser.add_argument("--exclude-reference", action="store_true",
                        help="drop reference-list chunks from the results")
    args = parser.parse_args()

    processed_dir = get_settings().data_dir / "corpus" / "processed"
    chunks = load_chunks(processed_dir) if processed_dir.exists() else []
    if not chunks:
        print("No ingested chunks found. Run scripts/corpus_fetch.py and scripts/corpus_ingest.py.")
        return 2
    manifest = load_manifest(MANIFEST)

    for hit in Bm25Retriever(chunks).search(args.query, args.top_k,
                                              exclude_reference=args.exclude_reference):
        citation = build_citation(hit.chunk, manifest.get(hit.chunk.doc_id))
        print(f"#{hit.rank}  score={hit.score:.3f}  [{hit.chunk.section_type}]")
        print(f"    {hit.chunk.chunk_id}")
        print(f"    {citation.formatted}")
        if citation.unverified_fields:
            print(f"    (unverified metadata: {', '.join(citation.unverified_fields)})")
        print(f"    {hit.chunk.text[: args.snippet_chars]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())