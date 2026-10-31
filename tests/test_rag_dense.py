"""Dense-retrieval tests. Offline: deterministic fake embedder, Qdrant :memory:.

No test here needs torch. Tests touching qdrant-client skip when the `dense`
extra is not installed; the one real-model check is additionally gated by
CLIMATEADAPT_RUN_DENSE_SMOKE=1 and downloads E5-small (~hundreds of MB).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
import types
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from climateadapt.rag.chunking import ChunkingParams
from climateadapt.rag.dense import (
    DenseIndexFingerprint,
    DenseRetriever,
    QdrantStore,
    StaleIndexError,
    collection_name,
    corpus_fingerprint,
    default_fingerprint_path,
    ensure_indexed,
    open_index,
    uniform_chunk_params,
)
from climateadapt.rag.embeddings import (
    E5_SMALL_MODEL_ID,
    E5Embedder,
    l2_normalize,
    prefix_passages,
    prefix_queries,
)
from climateadapt.rag.models import Chunk
from climateadapt.rag.retrieval import Bm25Retriever, HybridRetriever
from rag_helpers import make_chunk

DIM = 8


class FakeEmbedder:
    """Deterministic, normalized, torch-free Embedder for tests."""

    model_id = "fake-embedder-test"
    dim = DIM
    device = "fake-cpu"
    revision = "fake-rev-1"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.seen.extend(texts)
        rows = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
            rng = random.Random(seed)
            rows.append([rng.gauss(0.0, 1.0) for _ in range(DIM)])
        return l2_normalize(np.array(rows)).tolist()

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(prefix_queries(texts))

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(prefix_passages(texts))


@pytest.fixture
def chunks() -> list[Chunk]:
    return [
        make_chunk(0, "supplemental irrigation stabilises rainfed wheat yields"),
        make_chunk(1, "deficit irrigation saves water in cotton and maize"),
        make_chunk(2, "standardized precipitation index gamma distribution fitting"),
    ]


@pytest.fixture
def mem_store():
    pytest.importorskip("qdrant_client")
    store = QdrantStore(None)
    yield store
    store.close()


def fingerprint_path(tmp_path: Path, *, dim: int = DIM) -> Path:
    name = collection_name(FakeEmbedder.model_id, dim, ChunkingParams())
    return default_fingerprint_path(tmp_path, name)


# ------------------------------------------------------------------ embeddings


def test_prefix_helpers_use_e5_task_prefixes():
    assert prefix_queries(["a"]) == ["query: a"]
    assert prefix_passages(["a"]) == ["passage: a"]


def test_l2_normalize_handles_zero_rows():
    out = l2_normalize(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert out[0].tolist() == pytest.approx([0.6, 0.8])
    assert out[1].tolist() == [0.0, 0.0]
    assert not np.isnan(out).any()


def test_fake_embedder_is_deterministic_and_normalized():
    first = FakeEmbedder().embed_passages(["hello world"])
    second = FakeEmbedder().embed_passages(["hello world"])
    assert first == second
    assert math.isclose(sum(v * v for v in first[0]), 1.0, rel_tol=1e-9)
    assert FakeEmbedder().embed_queries(["hello world"]) != first


def test_e5_embedder_applies_prefixes_without_torch(monkeypatch):
    seen: dict = {}

    class StubModel:
        def encode(self, inputs, **kwargs):
            seen["inputs"] = inputs
            seen["normalize"] = kwargs["normalize_embeddings"]
            return np.ones((len(inputs), 4))

    monkeypatch.setattr(E5Embedder, "_load_model", lambda self: StubModel())
    embedder = E5Embedder()
    assert embedder.model_id == E5_SMALL_MODEL_ID
    assert embedder.embed_queries(["q"]) == [[1.0] * 4]
    assert seen["inputs"] == ["query: q"]
    assert seen["normalize"] is True
    embedder.embed_passages(["p"])
    assert seen["inputs"] == ["passage: p"]


def test_num_threads_is_applied_on_load(monkeypatch):
    torch = pytest.importorskip("torch")

    class StubModel:
        def encode(self, inputs, **kwargs):
            return np.ones((len(inputs), 4))

    stub_module = types.ModuleType("sentence_transformers")
    stub_module.SentenceTransformer = lambda *a, **k: StubModel()
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub_module)
    previous = torch.get_num_threads()
    try:
        E5Embedder(num_threads=2).embed_queries(["q"])
        assert torch.get_num_threads() == 2
    finally:
        torch.set_num_threads(previous)
    with pytest.raises(ValueError, match="num_threads"):
        E5Embedder(num_threads=0)


def test_missing_dense_extra_explains_itself(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    monkeypatch.setitem(sys.modules, "qdrant_client", None)
    with pytest.raises(ImportError, match="dense"):
        E5Embedder().embed_queries(["q"])
    with pytest.raises(ImportError, match="dense"):
        QdrantStore(None)


# ---------------------------------------------------------------- fingerprints


def test_corpus_fingerprint_is_stable_and_sensitive(chunks):
    assert corpus_fingerprint(chunks) == corpus_fingerprint(list(reversed(chunks)))
    other = chunks[0].model_copy(update={"text_sha256": "0" * 64})
    assert corpus_fingerprint([other, *chunks[1:]]) != corpus_fingerprint(chunks)


def test_collection_name_binds_model_dim_and_params():
    base = collection_name("m", 8, ChunkingParams())
    assert collection_name("m", 8, ChunkingParams()) == base
    assert collection_name("other", 8, ChunkingParams()) != base
    assert collection_name("m", 16, ChunkingParams()) != base
    assert collection_name("m", 8, ChunkingParams(chunk_words=100)) != base


def test_uniform_chunk_params_rejects_mixed_or_missing(tmp_path):
    good = {"chunk_words": 220, "overlap_words": 40, "min_words": 30,
            "min_alpha_ratio": 0.45, "max_page_span": None}
    for doc in ("a", "b"):
        (tmp_path / doc).mkdir()
        (tmp_path / doc / "meta.json").write_text(
            json.dumps({"chunking_params": good}), encoding="utf-8"
        )
    assert uniform_chunk_params(tmp_path, ["a", "b"]) == ChunkingParams()
    (tmp_path / "b" / "meta.json").write_text(
        json.dumps({"chunking_params": {**good, "chunk_words": 100}}), encoding="utf-8"
    )
    with pytest.raises(StaleIndexError, match="different parameters"):
        uniform_chunk_params(tmp_path, ["a", "b"])
    with pytest.raises(StaleIndexError, match="Missing"):
        uniform_chunk_params(tmp_path, ["a", "ghost"])


# ------------------------------------------------------------------- indexing


def test_index_build_is_idempotent(chunks, mem_store, tmp_path):
    fp_path = fingerprint_path(tmp_path)
    first, built, reason = ensure_indexed(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fp_path,
    )
    assert built and reason == "no-fingerprint"
    assert isinstance(first, DenseIndexFingerprint)
    assert first.n_points == 3 and first.embedding_dim == DIM
    second, rebuilt, reason2 = ensure_indexed(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fp_path,
    )
    assert not rebuilt and reason2 == "up-to-date"
    assert second == first
    _, forced, reason3 = ensure_indexed(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fp_path, force=True,
    )
    assert forced and reason3 == "force"


def test_changed_inputs_trigger_rebuild_not_silent_reuse(chunks, mem_store, tmp_path):
    fp_path = fingerprint_path(tmp_path)
    ensure_indexed(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fp_path,
    )
    _, built, reason = ensure_indexed(
        chunks[:2], embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fp_path,
    )
    assert built and reason.startswith("fingerprint-mismatch")


def test_open_refuses_stale_or_missing_indexes(chunks, mem_store, tmp_path):
    fp_path = fingerprint_path(tmp_path)
    with pytest.raises(StaleIndexError, match="rag_index"):
        open_index(
            chunks, embedder=FakeEmbedder(), store=mem_store,
            params=ChunkingParams(), fingerprint_path=fp_path,
        )
    ensure_indexed(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fp_path,
    )
    tampered = DenseIndexFingerprint.model_validate_json(fp_path.read_text(encoding="utf-8"))
    fp_path.write_text(
        tampered.model_copy(update={"corpus_sha256": "0" * 64}).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(StaleIndexError, match="corpus_sha256") as excinfo:
        open_index(
            chunks, embedder=FakeEmbedder(), store=mem_store,
            params=ChunkingParams(), fingerprint_path=fp_path,
        )
    assert "--force" in str(excinfo.value) and "rag_index" in str(excinfo.value)


def test_indexing_empty_chunks_is_an_error(mem_store, tmp_path):
    with pytest.raises(ValueError, match="empty chunk list"):
        ensure_indexed(
            [], embedder=FakeEmbedder(), store=mem_store,
            params=ChunkingParams(), fingerprint_path=tmp_path / "x.json",
        )


# ------------------------------------------------------------------ retrieval


def test_dense_search_rejoins_full_chunks(chunks, mem_store, tmp_path):
    retriever = DenseRetriever(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fingerprint_path(tmp_path),
    )
    hits = retriever.search("irrigation", top_k=2)
    assert [h.rank for h in hits] == [1, 2]
    assert all(isinstance(h.chunk, Chunk) and h.chunk.text for h in hits)
    assert hits[0].component_ranks == {"dense": 1}
    assert hits[0].component_scores == {"dense": hits[0].score}
    again = retriever.search("irrigation", top_k=2)
    assert [h.chunk.chunk_id for h in again] == [h.chunk.chunk_id for h in hits]


def test_dense_search_honours_exclude_reference(mem_store, tmp_path):
    chunks = [
        make_chunk(0, "supplemental irrigation wheat yields"),
        make_chunk(1, "Smith 2001 Jones 2005 bibliography", section_type="references"),
    ]
    retriever = DenseRetriever(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fingerprint_path(tmp_path),
    )
    assert len(retriever.search("irrigation", top_k=5)) == 2
    filtered = retriever.search("irrigation", top_k=5, exclude_reference=True)
    assert [h.chunk.chunk_id for h in filtered] == [chunks[0].chunk_id]
    assert filtered[0].rank == 1


def test_hybrid_fuses_real_bm25_and_dense(chunks, mem_store, tmp_path):
    dense = DenseRetriever(
        chunks, embedder=FakeEmbedder(), store=mem_store,
        params=ChunkingParams(), fingerprint_path=fingerprint_path(tmp_path),
    )
    hybrid = HybridRetriever([Bm25Retriever(chunks), dense])
    hits = hybrid.search("supplemental irrigation", top_k=3)
    assert hits and all(h.rank >= 1 for h in hits)
    assert set(hits[0].component_ranks) <= {"bm25", "dense"}
    assert set(hits[0].component_scores) == set(hits[0].component_ranks)
    assert any("dense" in h.component_ranks for h in hits)


# ---------------------------------------------------------------- gated smoke


@pytest.mark.skipif(
    os.environ.get("CLIMATEADAPT_RUN_DENSE_SMOKE") != "1",
    reason="Real-model smoke needs CLIMATEADAPT_RUN_DENSE_SMOKE=1 (downloads E5-small).",
)
def test_e5_small_smoke_on_cpu():
    pytest.importorskip("sentence_transformers")
    embedder = E5Embedder(device="cpu")
    assert embedder.dim == 384
    queries = embedder.embed_queries(["supplemental irrigation"])
    passages = embedder.embed_passages(["supplemental irrigation"])
    assert len(queries[0]) == 384
    assert math.isclose(sum(v * v for v in queries[0]), 1.0, rel_tol=1e-5)
    assert queries != passages  # prefixes change the encoding
    assert queries == embedder.embed_queries(["supplemental irrigation"])
    assert embedder.device == "cpu"
