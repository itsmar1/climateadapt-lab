import pytest

from climateadapt.rag.chunking import (
    ChunkingParams,
    chunk_document,
    section_type_of,
    verify_chunk_provenance,
)
from climateadapt.rag.models import Page
from climateadapt.rag.text import normalize_text, words


def test_normalisation_rules():
    assert normalize_text("the \ufb01rst  \u00a0 test") == "the first test"
    assert normalize_text("Chapter 1 ........... 5") == "Chapter 1 5"
    assert normalize_text("wa-\nter use") == "water use"
    assert normalize_text("well-known method") == "well-known method"
    assert normalize_text("co\u00adoperation") == "cooperation"
    assert words("  a\n\tb  ") == ["a", "b"]


def numbered_pages(per_page=100, n_pages=2):
    pages = []
    for p in range(n_pages):
        text = " ".join(f"w{p * per_page + i:04d}" for i in range(per_page))
        pages.append(Page(page=p + 1, text=text))
    return pages


def test_windows_overlap_and_track_pages():
    params = ChunkingParams(chunk_words=60, overlap_words=10, min_words=5, min_alpha_ratio=0.0)
    chunks, stats = chunk_document("doc-a", numbered_pages(), params)

    assert [c.chunk_id for c in chunks] == [f"doc-a:{i:05d}" for i in range(4)]
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (1, 2), (2, 2), (2, 2)]
    assert [c.word_count for c in chunks] == [60, 60, 60, 50]
    assert chunks[1].text.split()[:10] == chunks[0].text.split()[-10:]
    assert (
        stats.n_pages,
        stats.n_empty_pages,
        stats.n_words,
        stats.n_chunks_kept,
    ) == (2, 0, 200, 4)


def test_every_chunk_verifies_against_its_pages():
    params = ChunkingParams(chunk_words=60, overlap_words=10, min_words=5, min_alpha_ratio=0.0)
    pages = numbered_pages()
    chunks, _ = chunk_document("doc-a", pages, params)

    assert all(verify_chunk_provenance(c, pages) for c in chunks)


def test_tampering_and_wrong_pages_fail_verification():
    params = ChunkingParams(chunk_words=60, overlap_words=10, min_words=5, min_alpha_ratio=0.0)
    pages = numbered_pages()
    chunks, _ = chunk_document("doc-a", pages, params)
    spanning = chunks[1]

    assert not verify_chunk_provenance(
        spanning.model_copy(update={"text": spanning.text + " x"}),
        pages,
    )
    assert not verify_chunk_provenance(spanning.model_copy(update={"page_start": 2}), pages)
    assert not verify_chunk_provenance(spanning.model_copy(update={"page_end": 1}), pages)
    assert not verify_chunk_provenance(spanning.model_copy(update={"page_end": 9}), pages)
    edited = [Page(page=1, text=pages[0].text.replace("w0030", "w9999")), pages[1]]
    assert not verify_chunk_provenance(chunks[0], edited)


def test_empty_pages_are_counted_and_skipped():
    params = ChunkingParams(chunk_words=60, overlap_words=10, min_words=5, min_alpha_ratio=0.0)
    pages = [
        Page(page=1, text="alpha " * 80),
        Page(page=2, text="  "),
        Page(page=3, text="beta " * 80),
    ]

    chunks, stats = chunk_document("doc-a", pages, params)

    assert stats.n_empty_pages == 1
    assert {c.page_start for c in chunks} <= {1, 3}


def test_number_heavy_windows_are_dropped_and_counted():
    numbers = Page(page=1, text=" ".join(str(1000 + i) for i in range(100)))
    prose = Page(page=2, text=" ".join(["irrigation scheduling improves water productivity"] * 20))

    chunks, stats = chunk_document(
        "doc-a",
        [numbers, prose],
        ChunkingParams(chunk_words=100, overlap_words=0, min_words=10),
    )

    assert stats.n_chunks_dropped_low_alpha == 1
    assert [c.page_start for c in chunks] == [2]
    assert chunks[0].chunk_index == 1  # the dropped window leaves a visible gap


def test_tiny_documents_are_dropped_and_counted():
    chunks, stats = chunk_document("doc-a", [Page(page=1, text="only a few words here")])
    assert chunks == []
    assert stats.n_chunks_dropped_short == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chunk_words": 10},
        {"chunk_words": 100, "overlap_words": 100},
        {"chunk_words": 100, "overlap_words": -1},
        {"min_words": 0},
        {"chunk_words": 50, "min_words": 60},
        {"min_alpha_ratio": 1.5},
        {"max_page_span": 0},
    ],
)
def test_invalid_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        ChunkingParams(**kwargs)


def test_section_tagger_marks_bibliographies():
    refs = " ".join(
        f"Smith, J. ({2000 + i}). Some title {i}. Journal of Examples." for i in range(6)
    )
    assert section_type_of(refs) == "references"
    assert section_type_of("References " + refs) == "references"
    headed = "Bibliographie " + "Dupont, P. (2001). Titre. Revue. " * 2
    assert section_type_of(headed) == "references"


def test_section_tagger_keeps_cited_body_text():
    body = (
        "Supplemental irrigation stabilises rainfed wheat yields (Smith 2001). "
        "Deficit irrigation saves water in cotton and maize (Jones 2005)."
    )
    assert section_type_of(body) == "body"


def test_chunks_carry_labels_and_spans_can_be_capped():
    pages = [
        Page(page=n, text=f"Content words for page {n}. " * 30, label=str(n))
        for n in (1, 2, 3)
    ]
    params = ChunkingParams(chunk_words=60, overlap_words=10, min_words=10)
    chunks, _ = chunk_document("doc-a", pages, params)
    assert all(c.label_start == str(c.page_start) for c in chunks)
    assert all(c.label_end == str(c.page_end) for c in chunks)
    assert max(c.page_end - c.page_start + 1 for c in chunks) >= 2
    capped, stats = chunk_document(
        "doc-a",
        pages,
        ChunkingParams(chunk_words=60, overlap_words=10, min_words=10, max_page_span=1),
    )
    assert all(c.page_end == c.page_start for c in capped)
    assert all(c.label_start == c.label_end for c in capped)
    assert stats.n_chunks_cut_for_span >= 1