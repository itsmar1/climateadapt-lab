"""Retrieval evaluation against a gold set.

Labels are DOCUMENT-level (optionally page-level). Metrics, per query then averaged:
* hit@k        - at least one of the top-k chunks belongs to a relevant document.
* doc_recall@k - fraction of the relevant documents that appear among the top-k chunks.
* MRR          - 1 / rank of the first chunk from a relevant document (0 if none in top-k).
Page-level versions use annotated page ranges and are computed only for annotated queries.
Queries whose relevant documents are all missing from the ingested corpus are SKIPPED and
reported; for the others, relevance is restricted to documents that were ingested.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from climateadapt.rag.manifest import Manifest
from climateadapt.rag.retrieval import Retriever


class RelevantPages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> RelevantPages:
        if self.page_end < self.page_start:
            raise ValueError("page_end must not be smaller than page_start.")
        return self


class EvalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: str = Field(min_length=3)
    language: str = "en"
    relevant_doc_ids: list[str] = Field(min_length=1)
    relevant_pages: list[RelevantPages] = Field(default_factory=list)
    relevance_basis: str = Field(min_length=5)
    notes: str | None = None


class EvalSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_version: int
    description: str
    queries: list[EvalQuery]

    @model_validator(mode="after")
    def _unique_ids(self) -> EvalSet:
        ids = [q.id for q in self.queries]
        if len(set(ids)) != len(ids):
            raise ValueError("Query ids must be unique.")
        return self


def load_eval_set(path: Path, manifest: Manifest | None = None) -> EvalSet:
    eval_set = EvalSet.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if manifest is not None:
        known = set(manifest.doc_ids)
        for query in eval_set.queries:
            unknown = (
                set(query.relevant_doc_ids)
                | {p.doc_id for p in query.relevant_pages}
            ) - known
            if unknown:
                raise ValueError(
                    f"Query {query.id} names documents not in the manifest: "
                    f"{sorted(unknown)}"
                )
    return eval_set


class RetrievedRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    chunk_id: str
    doc_id: str
    page_start: int
    page_end: int


class QueryOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    language: str
    relevant_doc_ids: list[str]
    first_relevant_rank: int | None
    hit_at: dict[int, bool]
    doc_recall_at: dict[int, float]
    page_annotated: bool
    page_first_hit_rank: int | None
    retrieved: list[RetrievedRef]


class Aggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_queries: int
    hit_rate_at: dict[int, float]
    doc_recall_at: dict[int, float]
    mrr: float
    n_page_queries: int
    page_hit_rate_at: dict[int, float]
    page_mrr: float


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retriever: str
    ks: list[int]
    top_k: int
    n_evaluated: int
    n_skipped: int
    skipped: dict[str, str]
    documents_missing: list[str]
    overall: Aggregate
    by_language: dict[str, Aggregate]
    outcomes: list[QueryOutcome]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _aggregate(outcomes: Sequence[QueryOutcome], ks: Sequence[int]) -> Aggregate:
    paged = [o for o in outcomes if o.page_annotated]
    return Aggregate(
        n_queries=len(outcomes),
        hit_rate_at={k: _mean([1.0 if o.hit_at[k] else 0.0 for o in outcomes]) for k in ks},
        doc_recall_at={k: _mean([o.doc_recall_at[k] for o in outcomes]) for k in ks},
        mrr=_mean(
            [
                1.0 / o.first_relevant_rank if o.first_relevant_rank else 0.0
                for o in outcomes
            ]
        ),
        n_page_queries=len(paged),
        page_hit_rate_at={
            k: _mean(
                [
                    1.0 if o.page_first_hit_rank and o.page_first_hit_rank <= k
                    else 0.0
                    for o in paged
                ]
            )
            for k in ks
        },
        page_mrr=_mean(
            [1.0 / o.page_first_hit_rank if o.page_first_hit_rank else 0.0 for o in paged]
        ),
    )


def evaluate(
    retriever: Retriever,
    eval_set: EvalSet,
    available_doc_ids: Collection[str],
    *,
    ks: Sequence[int] = (1, 3, 5, 10),
    top_k: int | None = None,
) -> EvalReport:
    ks = sorted(set(ks))
    depth = max(ks) if top_k is None else top_k
    if depth < max(ks):
        raise ValueError("top_k must be at least max(ks).")
    available = set(available_doc_ids)

    outcomes: list[QueryOutcome] = []
    skipped: dict[str, str] = {}
    missing: set[str] = set()
    for query in eval_set.queries:
        relevant = set(query.relevant_doc_ids) & available
        missing |= set(query.relevant_doc_ids) - available
        if not relevant:
            skipped[query.id] = "none of the relevant documents is ingested"
            continue
        annotations = [p for p in query.relevant_pages if p.doc_id in available]
        hits = retriever.search(query.query, depth)

        first = next((h.rank for h in hits if h.chunk.doc_id in relevant), None)
        page_first = next(
            (
                h.rank
                for h in hits
                if any(
                    h.chunk.doc_id == p.doc_id
                    and h.chunk.page_start <= p.page_end
                    and h.chunk.page_end >= p.page_start
                    for p in annotations
                )
            ),
            None,
        )
        outcomes.append(
            QueryOutcome(
                query_id=query.id,
                language=query.language,
                relevant_doc_ids=sorted(relevant),
                first_relevant_rank=first,
                hit_at={k: first is not None and first <= k for k in ks},
                doc_recall_at={
                    k: len(relevant & {h.chunk.doc_id for h in hits if h.rank <= k}) / len(relevant)
                    for k in ks
                },
                page_annotated=bool(annotations),
                page_first_hit_rank=page_first,
                retrieved=[
                    RetrievedRef(
                        rank=h.rank,
                        chunk_id=h.chunk.chunk_id,
                        doc_id=h.chunk.doc_id,
                        page_start=h.chunk.page_start,
                        page_end=h.chunk.page_end,
                    )
                    for h in hits
                ],
            )
        )

    languages = sorted({o.language for o in outcomes})
    return EvalReport(
        retriever=getattr(retriever, "name", type(retriever).__name__),
        ks=list(ks),
        top_k=depth,
        n_evaluated=len(outcomes),
        n_skipped=len(skipped),
        skipped=skipped,
        documents_missing=sorted(missing),
        overall=_aggregate(outcomes, ks),
        by_language={
            lang: _aggregate([o for o in outcomes if o.language == lang], ks) for lang in languages
        },
        outcomes=outcomes,
    )