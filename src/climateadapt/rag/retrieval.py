"""Retrievers behind one interface, plus hybrid fusion of any number of them."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from climateadapt.rag.bm25 import BM25Index
from climateadapt.rag.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion
from climateadapt.rag.models import Chunk, RetrievedChunk


class Retriever(Protocol):
    name: str

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]: ...


class Bm25Retriever:
    name = "bm25"

    def __init__(self, chunks: Sequence[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._index = BM25Index(chunks, k1=k1, b=b)

    def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        chunks = self._index.chunks
        return [
            RetrievedChunk(
                chunk=chunks[position],
                score=score,
                rank=rank,
                component_ranks={self.name: rank},
                component_scores={self.name: score},
            )
            for rank, (position, score) in enumerate(self._index.search(query, top_k), start=1)
        ]


class HybridRetriever:
    """Fuse component retrievers with Reciprocal Rank Fusion."""

    name = "hybrid"

    def __init__(
        self,
        retrievers: Sequence[Retriever],
        *,
        rrf_k: int = DEFAULT_RRF_K,
        candidate_depth: int = 50,
    ) -> None:
        names = [retriever.name for retriever in retrievers]
        if not retrievers or len(set(names)) != len(names):
            raise ValueError("Provide at least one retriever, each with a unique name.")
        if candidate_depth < 1:
            raise ValueError("candidate_depth must be at least 1.")
        self._retrievers = list(retrievers)
        self._rrf_k = rrf_k
        self._depth = candidate_depth

    def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        rankings: dict[str, list[str]] = {}
        chunks: dict[str, Chunk] = {}
        scores: dict[str, dict[str, float]] = {}
        for retriever in self._retrievers:
            hits = retriever.search(query, self._depth)
            rankings[retriever.name] = [hit.chunk.chunk_id for hit in hits]
            scores[retriever.name] = {hit.chunk.chunk_id: hit.score for hit in hits}
            for hit in hits:
                chunks[hit.chunk.chunk_id] = hit.chunk
        fused = reciprocal_rank_fusion(rankings, k=self._rrf_k, top_k=top_k)
        return [
            RetrievedChunk(
                chunk=chunks[item.chunk_id],
                score=item.score,
                rank=rank,
                component_ranks=dict(item.ranks),
                component_scores={s: scores[s][item.chunk_id] for s in item.ranks},
            )
            for rank, item in enumerate(fused, start=1)
        ]