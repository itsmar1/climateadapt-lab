import math

import pytest

from climateadapt.rag.bm25 import BM25Index, tokenize
from climateadapt.rag.fusion import reciprocal_rank_fusion
from climateadapt.rag.models import RetrievedChunk
from climateadapt.rag.retrieval import Bm25Retriever, HybridRetriever
from rag_helpers import make_chunk


def test_tokenisation_is_unicode_aware_and_case_folded():
    assert tokenize("Irrigation d'\u00e9t\u00e9, \u00c9T\u00c9 2024!") == [
        "irrigation", "d", "\u00e9t\u00e9", "\u00e9t\u00e9", "2024"
    ]
    assert tokenize(
        "\u0627\u0644\u0631\u064a \u0627\u0644\u062a\u0643\u0645\u064a\u0644\u064a"
    ) == [
        "\u0627\u0644\u0631\u064a", "\u0627\u0644\u062a\u0643\u0645\u064a\u0644\u064a"
    ]


def equal_length_chunks():
    return [
        make_chunk(0, "alpha beta gamma"),
        make_chunk(1, "delta epsilon zeta"),
        make_chunk(2, "eta theta iota"),
        make_chunk(3, "kappa lambda mu"),
    ]


def test_score_of_a_single_rare_term_equals_its_idf_when_lengths_are_equal():
    hits = BM25Index(equal_length_chunks()).search("alpha")

    assert [position for position, _ in hits] == [0]
    # N = 4, n = 1: ln(1 + 3.5 / 1.5) = 1.2039728; tf = 1 and length norm = 1 give a factor of 1.
    assert hits[0][1] == pytest.approx(1.2039728, abs=1e-6)
    assert hits[0][1] == pytest.approx(math.log(1 + 3.5 / 1.5))


def test_term_frequency_saturates_by_the_bm25_formula():
    chunks = [
        make_chunk(0, "water x1 x2"),
        make_chunk(1, "water water x1"),
        make_chunk(2, "other words here"),
    ]
    (first, a), (second, b) = BM25Index(chunks).search("water")

    assert (first, second) == (1, 0)
    # k1 = 1.5, equal lengths: tf=2 gives 2*2.5/(2+1.5) = 1.428571 times the tf=1 score.
    assert b / a == pytest.approx(1.0 / 1.4285714, rel=1e-6)


def test_shorter_chunks_win_for_the_same_term_frequency():
    chunks = [
        make_chunk(0, "water"),
        make_chunk(1, "water " + " ".join(f"filler{i}" for i in range(20))),
        make_chunk(2, "unrelated words entirely"),
    ]
    ranked = [position for position, _ in BM25Index(chunks).search("water")]
    assert ranked == [0, 1]


def test_rare_terms_outweigh_common_ones():
    chunks = [
        make_chunk(0, "water crop"),
        make_chunk(1, "water soil"),
        make_chunk(2, "water rotation"),
        make_chunk(3, "salinity soil"),
    ]
    index = BM25Index(chunks)
    assert index.idf("salinity") > index.idf("water")
    assert [p for p, _ in index.search("water salinity")][0] == 3


def test_unknown_and_empty_queries_return_nothing_and_ties_break_by_position():
    index = BM25Index([make_chunk(0, "same words"), make_chunk(1, "same words")])
    assert index.search("nothing") == []
    assert index.search("") == []
    assert [p for p, _ in index.search("same")] == [0, 1]
    assert len(index.search("same", top_k=1)) == 1
    assert BM25Index([]).search("anything") == []
    with pytest.raises(ValueError):
        index.search("same", top_k=0)


@pytest.mark.parametrize("kwargs", [{"k1": -1.0}, {"b": 1.5}, {"b": -0.1}])
def test_invalid_bm25_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        BM25Index([make_chunk(0, "a b c")], **kwargs)


# ---------------------------------------------------------------- reciprocal rank fusion


def test_rrf_scores_and_ties_by_hand():
    fused = reciprocal_rank_fusion({"a": ["x", "y", "z"], "b": ["y", "x", "w"]}, k=60)

    scores = {hit.chunk_id: hit.score for hit in fused}
    assert scores["x"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["y"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["z"] == pytest.approx(1 / 63)
    assert [hit.chunk_id for hit in fused] == ["x", "y", "w", "z"]  # ties by id
    assert fused[0].ranks == {"a": 1, "b": 2}


def test_rrf_rewards_agreement_between_rankings():
    fused = reciprocal_rank_fusion({"a": ["x", "y"], "b": ["y", "z"], "c": ["y"]})
    assert [hit.chunk_id for hit in fused][0] == "y"


def test_rrf_top_k_and_validation():
    rankings = {"a": ["x", "y", "z"]}
    assert [h.chunk_id for h in reciprocal_rank_fusion(rankings, top_k=2)] == ["x", "y"]
    for bad_k in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            reciprocal_rank_fusion(rankings, k=bad_k)
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(rankings, top_k=0)
    with pytest.raises(ValueError, match="duplicate"):
        reciprocal_rank_fusion({"a": ["x", "x"]})
    assert reciprocal_rank_fusion({}) == []


# ---------------------------------------------------------------- retrievers


class StubRetriever:
    def __init__(self, name, chunks):
        self.name = name
        self._chunks = chunks
        self.requested = []

    def search(self, query, top_k):
        self.requested.append(top_k)
        return [
            RetrievedChunk(
                chunk=chunk,
                score=10.0 - rank,
                rank=rank,
                component_ranks={self.name: rank},
                component_scores={self.name: 10.0 - rank},
            )
            for rank, chunk in enumerate(self._chunks[:top_k], start=1)
        ]


def four_chunks():
    return [make_chunk(i, f"text number {i}") for i in range(1, 5)]


def test_hybrid_fuses_components_and_keeps_their_ranks_and_scores():
    c1, c2, c3, c4 = four_chunks()
    first = StubRetriever("lexical", [c1, c2, c3])
    second = StubRetriever("dense", [c2, c1, c4])

    hits = HybridRetriever([first, second], rrf_k=60, candidate_depth=7).search("q", top_k=4)

    assert [h.chunk.chunk_id for h in hits] == [c1.chunk_id, c2.chunk_id, c3.chunk_id, c4.chunk_id]
    assert [h.rank for h in hits] == [1, 2, 3, 4]
    assert hits[1].component_ranks == {"lexical": 2, "dense": 1}
    assert hits[1].component_scores == {"lexical": 8.0, "dense": 9.0}
    assert hits[2].component_ranks == {"lexical": 3}
    assert first.requested == second.requested == [7]
    assert len(HybridRetriever([first, second]).search("q", top_k=2)) == 2


def test_hybrid_rejects_missing_or_duplicate_retrievers():
    stub = StubRetriever("a", [])
    with pytest.raises(ValueError):
        HybridRetriever([])
    with pytest.raises(ValueError):
        HybridRetriever([stub, StubRetriever("a", [])])
    with pytest.raises(ValueError):
        HybridRetriever([stub], candidate_depth=0)


def test_bm25_retriever_returns_ranked_chunks_with_scores():
    chunks = [make_chunk(0, "supplemental irrigation wheat"), make_chunk(1, "deficit irrigation")]
    hits = Bm25Retriever(chunks).search("supplemental irrigation", top_k=5)

    assert [h.chunk.chunk_id for h in hits][0] == chunks[0].chunk_id
    assert [h.rank for h in hits] == [1, 2]
    assert hits[0].component_scores == {"bm25": hits[0].score}