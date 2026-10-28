"""End-to-end offline retrieval on a synthetic three-document corpus."""

from __future__ import annotations

import pytest

from climateadapt.rag.chunking import ChunkingParams
from climateadapt.rag.citations import build_citation, verify_citation
from climateadapt.rag.evaluation import EvalSet, evaluate
from climateadapt.rag.ingest import ingest_document, load_chunks, load_pages, processed_doc_ids
from climateadapt.rag.manifest import Manifest
from climateadapt.rag.retrieval import Bm25Retriever
from rag_helpers import make_pdf
from test_rag_manifest import valid_doc

PARAMS = ChunkingParams(chunk_words=40, overlap_words=10, min_words=10)

TEXTS = {
    "doc-irrigation": [
        "Supplemental irrigation stabilises rainfed wheat yields during dry spells in drylands.",
        "Applying limited water at critical growth stages raises water productivity of wheat.",
    ],
    "doc-spi": [
        (
            "The standardized precipitation index fits a gamma "
            "distribution to monthly rainfall totals."
        ),
        "A reference period of thirty years of precipitation records is recommended for the index.",
    ],
    "doc-reanalysis": [
        "A land surface reanalysis forced by atmospheric fields provides hourly soil moisture.",
        "The reanalysis grid has a native resolution of nine kilometres over all land areas.",
    ],
}


@pytest.fixture
def corpus(tmp_path):
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    documents = []
    for index, (doc_id, sentences) in enumerate(TEXTS.items()):
        documents.append(
            valid_doc(
                doc_id=doc_id,
                title=f"Synthetic document {index}",
                access="manual",
                pdf_urls=[],
            )
        )
        pages = ["\n".join([sentence] * 8) for sentence in sentences]
        (raw / f"{doc_id}.pdf").write_bytes(make_pdf(pages))
    manifest = Manifest.model_validate(
        {"manifest_version": 1, "description": "synthetic", "documents": documents}
    )
    for doc in manifest.documents:
        ingest_document(doc, raw_dir=raw, processed_dir=processed, params=PARAMS)
    return manifest, processed


def eval_set(pages=None):
    queries = [
        ("q1", "supplemental irrigation of rainfed wheat", ["doc-irrigation"]),
        ("q2", "gamma distribution precipitation index", ["doc-spi"]),
        ("q3", "reanalysis soil moisture resolution", ["doc-reanalysis"]),
    ]
    payload = {
        "eval_version": 1,
        "description": "synthetic",
        "queries": [
            {"id": qid, "query": q, "relevant_doc_ids": docs, "relevance_basis": "synthetic corpus"}
            for qid, q, docs in queries
        ],
    }
    if pages:
        payload["queries"][0]["relevant_pages"] = pages
    return EvalSet.model_validate(payload)


def test_every_retrieved_chunk_has_a_correct_traceable_citation(corpus):
    manifest, processed = corpus
    pages_by_doc = {
        doc_id: load_pages(processed, doc_id)
        for doc_id in processed_doc_ids(processed)
    }
    retriever = Bm25Retriever(load_chunks(processed))

    for query in ("rainfed wheat yields", "gamma distribution", "soil moisture reanalysis"):
        hits = retriever.search(query, top_k=5)
        assert hits
        for hit in hits:
            assert verify_citation(hit.chunk, manifest, pages_by_doc) == []
            citation = build_citation(hit.chunk, manifest.get(hit.chunk.doc_id))
            assert citation.doc_id == hit.chunk.doc_id
            assert citation.pages.startswith("p")


def test_perfect_retrieval_on_the_synthetic_gold_set(corpus):
    manifest, processed = corpus
    report = evaluate(
        Bm25Retriever(load_chunks(processed)),
        eval_set(),
        processed_doc_ids(processed),
    )

    assert report.n_evaluated == 3 and report.n_skipped == 0
    assert report.overall.hit_rate_at[1] == 1.0
    assert report.overall.doc_recall_at[3] == 1.0
    assert report.overall.mrr == 1.0
    assert report.by_language["en"].n_queries == 3
    assert report.overall.n_page_queries == 0


def test_queries_for_missing_documents_are_skipped_and_reported(corpus):
    _, processed = corpus
    available = processed_doc_ids(processed) - {"doc-reanalysis"}
    report = evaluate(
        Bm25Retriever(load_chunks(processed, sorted(available))),
        eval_set(),
        available,
    )

    assert report.n_evaluated == 2 and report.n_skipped == 1
    assert report.skipped == {"q3": "none of the relevant documents is ingested"}
    assert report.documents_missing == ["doc-reanalysis"]


def test_page_level_metrics_use_annotated_pages(corpus):
    _, processed = corpus
    retriever = Bm25Retriever(load_chunks(processed))

    covered = evaluate(
        retriever,
        eval_set([{"doc_id": "doc-irrigation", "page_start": 1, "page_end": 2}]),
        processed_doc_ids(processed),
    )
    uncovered = evaluate(
        retriever,
        eval_set([{"doc_id": "doc-irrigation", "page_start": 99, "page_end": 99}]),
        processed_doc_ids(processed),
    )

    assert covered.overall.n_page_queries == 1 and covered.overall.page_mrr == 1.0
    first = covered.outcomes[0]
    assert first.page_first_hit_rank == 1
    assert uncovered.overall.page_mrr == 0.0
    assert uncovered.outcomes[0].first_relevant_rank == 1  # document-level hit is unaffected


def test_misses_are_visible_per_query(corpus):
    _, processed = corpus
    payload = {
        "eval_version": 1,
        "description": "synthetic",
        "queries": [
            {
                "id": "qx",
                "query": "completely unrelated zebra vocabulary",
                "language": "fr",
                "relevant_doc_ids": ["doc-spi"],
                "relevance_basis": "synthetic miss",
            }
        ],
    }
    report = evaluate(
        Bm25Retriever(load_chunks(processed)),
        EvalSet.model_validate(payload),
        processed_doc_ids(processed),
    )
    outcome = report.outcomes[0]
    assert outcome.first_relevant_rank is None
    assert outcome.retrieved == []
    assert report.overall.mrr == 0.0 and report.by_language["fr"].hit_rate_at[10] == 0.0