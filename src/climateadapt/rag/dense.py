"""Dense retrieval over a Qdrant local collection, guarded by fingerprints.

Every index records HOW it was built (embedding model id + revision,
embedding dimension, device, chunking parameters, corpus hash). Opening an
index verifies the fingerprint first: a stale or mixed index raises
``StaleIndexError`` with rebuild instructions instead of serving wrong
results. Retrieved text always rejoins the chunk store by ``chunk_id`` —
Qdrant payloads carry ids, never the authoritative text.

``qdrant-client`` is optional: it is imported lazily so the base package
and offline tests run without the ``dense`` extra.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from climateadapt.rag.chunking import ChunkingParams
from climateadapt.rag.embeddings import Embedder
from climateadapt.rag.models import Chunk, RetrievedChunk

DENSE_FORMAT_VERSION = 1


class StaleIndexError(Exception):
    """A dense index is missing, stale, or built from different inputs."""


class DenseIndexFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dense_format_version: int = DENSE_FORMAT_VERSION
    collection: str
    model_id: str
    model_revision: str
    embedding_dim: int
    device: str
    chunk_params: dict[str, Any]
    corpus_sha256: str
    n_points: int
    created_at_utc: str


def corpus_fingerprint(chunks: Sequence[Chunk]) -> str:
    """Hash over sorted ``chunk_id`` + ``text_sha256`` pairs (covers all text)."""
    digest = hashlib.sha256()
    for chunk in sorted(chunks, key=lambda c: c.chunk_id):
        digest.update(chunk.chunk_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(chunk.text_sha256.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def chunk_params_dict(params: ChunkingParams) -> dict[str, Any]:
    return {
        "chunk_words": params.chunk_words,
        "overlap_words": params.overlap_words,
        "min_words": params.min_words,
        "min_alpha_ratio": params.min_alpha_ratio,
        "max_page_span": params.max_page_span,
    }


def collection_name(model_id: str, dim: int, params: ChunkingParams) -> str:
    """Collection name binding model + dimension + chunking config."""
    slug = model_id.replace("/", "-").replace(".", "-").replace("_", "-")
    config = json.dumps(
        {"model_id": model_id, "dim": dim, "chunk_params": chunk_params_dict(params)},
        sort_keys=True,
    )
    tag = hashlib.sha256(config.encode("utf-8")).hexdigest()[:8]
    return f"climateadapt-{slug}-{dim}d-{tag}"


def default_fingerprint_path(qdrant_dir: Path, collection: str) -> Path:
    return qdrant_dir / f"{collection}.fingerprint.json"


def uniform_chunk_params(processed_dir: Path, doc_ids: Sequence[str]) -> ChunkingParams:
    """Chunking params shared by every doc; refuse mixed or missing configs."""
    seen: dict[str, dict[str, Any]] = {}
    for doc_id in sorted(doc_ids):
        meta_path = processed_dir / doc_id / "meta.json"
        if not meta_path.exists():
            raise StaleIndexError(
                f"Missing {meta_path}; re-run scripts/corpus_ingest.py first."
            )
        seen[doc_id] = json.loads(meta_path.read_text(encoding="utf-8"))["chunking_params"]
    first = next(iter(seen.values()))
    if any(params != first for params in seen.values()):
        detail = "; ".join(f"{d}={p}" for d, p in sorted(seen.items()))
        raise StaleIndexError(
            "Refusing dense indexing: documents were chunked with different "
            f"parameters ({detail}). Re-ingest uniformly first."
        )
    return ChunkingParams(**first)


class QdrantStore:
    """Thin wrapper over Qdrant local mode (persisted dir or ``:memory:``)."""

    def __init__(self, path: Path | None) -> None:
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise ImportError(
                "Dense retrieval needs the 'dense' extra: "
                "run `uv sync --extra dense`."
            ) from exc
        if path is not None:
            path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(path))
        else:
            self._client = QdrantClient(":memory:")
        self._path = path

    @property
    def path(self) -> Path | None:
        return self._path

    def collection_exists(self, collection: str) -> bool:
        return bool(self._client.collection_exists(collection))

    def ensure_collection(self, collection: str, dim: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not self.collection_exists(collection):
            self._client.create_collection(
                collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def delete_collection(self, collection: str) -> None:
        if self.collection_exists(collection):
            self._client.delete_collection(collection)

    def upsert(
        self, collection: str, vectors: Sequence[Sequence[float]], chunks: Sequence[Chunk]
    ) -> None:
        from qdrant_client.models import PointStruct

        self._client.upsert(
            collection,
            [
                PointStruct(
                    id=index,
                    vector=list(vector),
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "doc_id": chunk.doc_id,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                    },
                )
                for index, (vector, chunk) in enumerate(zip(vectors, chunks, strict=True))
            ],
        )

    def count(self, collection: str) -> int:
        return int(self._client.count(collection).count)

    def search(self, collection: str, vector: Sequence[float], limit: int) -> list[Any]:
        return list(
            self._client.query_points(collection, query=list(vector), limit=limit).points
        )

    def close(self) -> None:
        self._client.close()


def _embedder_revision(embedder: Embedder) -> str:
    revision = getattr(embedder, "revision", None)
    return revision if isinstance(revision, str) else "unknown:no-revision"


def expected_fingerprint(
    *,
    chunks: Sequence[Chunk],
    embedder: Embedder,
    params: ChunkingParams,
) -> DenseIndexFingerprint:
    collection = collection_name(embedder.model_id, embedder.dim, params)
    return DenseIndexFingerprint(
        collection=collection,
        model_id=embedder.model_id,
        model_revision=_embedder_revision(embedder),
        embedding_dim=embedder.dim,
        device=embedder.device,
        chunk_params=chunk_params_dict(params),
        corpus_sha256=corpus_fingerprint(chunks),
        n_points=len(chunks),
        created_at_utc=datetime.now(UTC).isoformat(),
    )


def _fingerprint_diff(
    stored: DenseIndexFingerprint, expected: DenseIndexFingerprint
) -> list[str]:
    diffs = []
    for field in (
        "dense_format_version",
        "collection",
        "model_id",
        "model_revision",
        "embedding_dim",
        "device",
        "chunk_params",
        "corpus_sha256",
    ):
        old, new = getattr(stored, field), getattr(expected, field)
        if old != new:
            diffs.append(f"{field}: stored={old!r} expected={new!r}")
    return diffs


def read_fingerprint(path: Path) -> DenseIndexFingerprint | None:
    if not path.exists():
        return None
    return DenseIndexFingerprint.model_validate_json(path.read_text(encoding="utf-8"))


def ensure_indexed(
    chunks: Sequence[Chunk],
    *,
    embedder: Embedder,
    store: QdrantStore,
    params: ChunkingParams,
    fingerprint_path: Path,
    force: bool = False,
) -> tuple[DenseIndexFingerprint, bool, str]:
    """Build the dense index unless a matching one already exists.

    Returns ``(fingerprint, built, reason)`` where ``built`` is False when
    the existing index was verified fresh (same collection, fingerprint,
    and point count). ``force=True`` deletes and rebuilds unconditionally.
    """
    if not chunks:
        raise ValueError("Cannot index an empty chunk list.")
    expected = expected_fingerprint(chunks=chunks, embedder=embedder, params=params)
    if not force:
        stored = read_fingerprint(fingerprint_path)
        if stored is None:
            reason = "no-fingerprint"
        elif diffs := _fingerprint_diff(stored, expected):
            fields = sorted({d.split(":")[0] for d in diffs})
            reason = f"fingerprint-mismatch:{','.join(fields)}"
        elif not store.collection_exists(expected.collection):
            reason = "missing-collection"
        elif store.count(expected.collection) != len(chunks):
            reason = (
                f"count-mismatch:collection-{store.count(expected.collection)}:"
                f"chunks-{len(chunks)}"
            )
        else:
            return stored, False, "up-to-date"
    else:
        reason = "force"
    vectors = embedder.embed_passages([c.text for c in chunks])
    if len(vectors) != len(chunks):
        raise ValueError(
            f"Embedder returned {len(vectors)} vectors for {len(chunks)} chunks."
        )
    # Re-resolve post-download: the first encode may have fetched the model.
    expected.model_revision = _embedder_revision(embedder)
    store.delete_collection(expected.collection)
    store.ensure_collection(expected.collection, expected.embedding_dim)
    store.upsert(expected.collection, vectors, chunks)
    fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint_path.write_text(expected.model_dump_json(indent=2), encoding="utf-8")
    return expected, True, reason


def open_index(
    chunks: Sequence[Chunk],
    *,
    embedder: Embedder,
    store: QdrantStore,
    params: ChunkingParams,
    fingerprint_path: Path,
) -> DenseIndexFingerprint:
    """Verify a previously built index; refuse stale or mixed ones loudly."""
    expected = expected_fingerprint(chunks=chunks, embedder=embedder, params=params)
    stored = read_fingerprint(fingerprint_path)
    if stored is None:
        raise StaleIndexError(
            f"No dense index fingerprint at {fingerprint_path}. "
            "Run `uv run python scripts/rag_index.py` to build it."
        )
    if diffs := _fingerprint_diff(stored, expected):
        raise StaleIndexError(
            "Dense index was built from different inputs:\n"
            + "\n".join(f"  - {d}" for d in diffs)
            + "\nRebuild it with `uv run python scripts/rag_index.py --force`."
        )
    if not store.collection_exists(expected.collection):
        raise StaleIndexError(
            f"Collection {expected.collection!r} is missing from the Qdrant store. "
            "Rebuild it with `uv run python scripts/rag_index.py --force`."
        )
    return stored


class DenseRetriever:
    """Qdrant-backed dense retriever behind the Retriever interface."""

    name = "dense"

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        embedder: Embedder,
        store: QdrantStore,
        params: ChunkingParams,
        fingerprint_path: Path,
        build: bool = True,
    ) -> None:
        self._chunks = list(chunks)
        self._by_id = {c.chunk_id: c for c in self._chunks}
        self._embedder = embedder
        self._store = store
        if build:
            fingerprint, _, _ = ensure_indexed(
                self._chunks,
                embedder=embedder,
                store=store,
                params=params,
                fingerprint_path=fingerprint_path,
            )
        else:
            fingerprint = open_index(
                self._chunks,
                embedder=embedder,
                store=store,
                params=params,
                fingerprint_path=fingerprint_path,
            )
        self._collection = fingerprint.collection

    def search(
        self, query: str, top_k: int = 10, *, exclude_reference: bool = False
    ) -> list[RetrievedChunk]:
        """Search dense vectors; ranks recomputed after reference filtering."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        vectors = self._embedder.embed_queries([query])
        depth = len(self._chunks) if exclude_reference else top_k
        scored = self._store.search(self._collection, vectors[0], depth) if depth >= 1 else []
        ranked: list[tuple[float, Chunk]] = []
        for point in scored:
            chunk_id = point.payload["chunk_id"]
            chunk = self._by_id.get(chunk_id)
            if chunk is None:
                raise StaleIndexError(
                    f"Qdrant point maps to unknown chunk {chunk_id!r}; "
                    "the index no longer matches the chunk store. "
                    "Rebuild it with `uv run python scripts/rag_index.py --force`."
                )
            if exclude_reference and chunk.section_type == "references":
                continue
            ranked.append((point.score, chunk))
            if len(ranked) >= top_k:
                break
        return [
            RetrievedChunk(
                chunk=chunk,
                score=float(score),
                rank=rank,
                component_ranks={self.name: rank},
                component_scores={self.name: float(score)},
            )
            for rank, (score, chunk) in enumerate(ranked, start=1)
        ]

    def close(self) -> None:
        self._store.close()
