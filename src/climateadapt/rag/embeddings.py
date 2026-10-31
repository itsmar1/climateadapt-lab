"""Multilingual E5-small embeddings (P07 small-model only).

E5 requires task prefixes: ``query: `` for queries, ``passage: `` for chunks.
Embeddings are L2-normalized so cosine similarity equals dot product.

``sentence-transformers`` (and torch) are optional: nothing here imports them
at module load, so the base package and offline tests run without the
``dense`` extra installed.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

E5_SMALL_MODEL_ID = "intfloat/multilingual-e5-small"
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


class Embedder(Protocol):
    """Any text embedder producing L2-normalized vectors (real or fake)."""

    model_id: str
    dim: int
    device: str

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...


def prefix_queries(texts: Sequence[str]) -> list[str]:
    return [QUERY_PREFIX + text for text in texts]


def prefix_passages(texts: Sequence[str]) -> list[str]:
    return [PASSAGE_PREFIX + text for text in texts]


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization; zero rows stay zero (never NaN)."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms > 0.0)


def resolve_hf_revision(model_id: str) -> str:
    """Best-effort resolved revision (commit sha) of a cached HF model.

    Scans the local Hugging Face hub cache only (stdlib; no network, no
    huggingface-hub import). Returns ``"unknown:<reason>"`` when the model
    is not cached or the cache is ambiguous — callers store the string as-is.
    """
    cache = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
    roots = [Path(cache)] if cache else []
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    snapshots: set[str] = set()
    for root in roots:
        snap_dir = root / ("models--" + model_id.replace("/", "--")) / "snapshots"
        if snap_dir.is_dir():
            snapshots.update(p.name for p in snap_dir.iterdir() if p.is_dir())
    if len(snapshots) == 1:
        return next(iter(snapshots))
    if not snapshots:
        return "unknown:not-cached"
    return f"unknown:{len(snapshots)}-snapshots"


class E5Embedder:
    """Lazily-loaded multilingual-e5-small encoder (CPU by default)."""

    def __init__(
        self,
        *,
        model_id: str = E5_SMALL_MODEL_ID,
        batch_size: int = 32,
        device: str = "cpu",
        show_progress: bool = False,
        num_threads: int | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1.")
        if num_threads is not None and num_threads < 1:
            raise ValueError("num_threads must be at least 1.")
        self._model_id = model_id
        self._batch_size = batch_size
        self._device = device
        self._show_progress = show_progress
        self._num_threads = num_threads
        self._model: Any | None = None
        self._dim: int | None = None
        self._revision: str | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        """Observed embedding dimension (one tiny probe encode, cached)."""
        if self._dim is None:
            probe = self._encode([QUERY_PREFIX + "dimension probe"])
            self._dim = len(probe[0])
        return self._dim

    @property
    def device(self) -> str:
        return self._device

    @property
    def revision(self) -> str:
        """Resolved model revision, best-effort (see resolve_hf_revision)."""
        if self._revision is None or self._revision.startswith("unknown:"):
            self._revision = resolve_hf_revision(self._model_id)
        return self._revision

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "Dense retrieval needs the 'dense' extra: "
                    "run `uv sync --extra dense`."
                ) from exc
            self._model = SentenceTransformer(self._model_id, device=self._device)
            if self._num_threads is not None:
                import torch

                torch.set_num_threads(self._num_threads)
        return self._model

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load_model()
        vectors = model.encode(
            list(texts),
            batch_size=self._batch_size,
            show_progress_bar=self._show_progress,
            normalize_embeddings=True,
        )
        return [list(map(float, row)) for row in np.asarray(vectors)]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(prefix_queries(texts))

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(prefix_passages(texts))
