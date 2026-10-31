"""Build (or verify) the dense E5/Qdrant index over the ingested corpus.

    uv run python scripts/rag_index.py
    uv run python scripts/rag_index.py --force

Re-running is safe: when the stored fingerprint matches the current model,
chunking parameters, and corpus, the index is left untouched. Any mismatch
rebuilds automatically (the reason is printed). To rebuild deliberately,
pass --force. The index lives under data/qdrant/ (git-ignored).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.rag.dense import (
    QdrantStore,
    StaleIndexError,
    collection_name,
    default_fingerprint_path,
    ensure_indexed,
    uniform_chunk_params,
)
from climateadapt.rag.embeddings import E5_SMALL_MODEL_ID, E5Embedder
from climateadapt.rag.ingest import load_chunks, processed_doc_ids


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="delete and rebuild")
    parser.add_argument("--device", default="cpu", help="torch device for encoding")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--threads", type=int, default=None,
                        help="torch intra-op threads (default: torch default)")
    parser.add_argument("--show-progress", action="store_true")
    parser.add_argument("--qdrant-dir", default=None, help="override data/qdrant")
    args = parser.parse_args()

    settings = get_settings()
    processed_dir = settings.data_dir / "corpus" / "processed"
    doc_ids = sorted(processed_doc_ids(processed_dir))
    chunks = load_chunks(processed_dir)
    if not chunks:
        print("No ingested chunks. Run scripts/corpus_ingest.py first.")
        return 2
    try:
        params = uniform_chunk_params(processed_dir, doc_ids)
    except StaleIndexError as exc:
        print(exc)
        return 2
    qdrant_dir = Path(args.qdrant_dir) if args.qdrant_dir else settings.data_dir / "qdrant"
    embedder = E5Embedder(
        model_id=E5_SMALL_MODEL_ID,
        batch_size=args.batch_size,
        device=args.device,
        show_progress=args.show_progress,
        num_threads=args.threads,
    )
    store = QdrantStore(qdrant_dir)
    try:
        fingerprint_path = default_fingerprint_path(
            qdrant_dir, collection_name(embedder.model_id, embedder.dim, params)
        )
        started = time.perf_counter()
        fingerprint, built, reason = ensure_indexed(
            chunks,
            embedder=embedder,
            store=store,
            params=params,
            fingerprint_path=fingerprint_path,
            force=args.force,
        )
        elapsed = time.perf_counter() - started
    finally:
        store.close()
    print(f"collection:  {fingerprint.collection}")
    print(f"model:       {fingerprint.model_id} rev={fingerprint.model_revision}")
    print(f"dim/device:  {fingerprint.embedding_dim} / {fingerprint.device}")
    print(f"points:      {fingerprint.n_points} over {len(doc_ids)} documents")
    print(f"corpus sha:  {fingerprint.corpus_sha256[:12]}...")
    print(f"result:      {'built' if built else 'up-to-date'} ({reason}) in {elapsed:.1f}s")
    print(f"fingerprint: {fingerprint_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
