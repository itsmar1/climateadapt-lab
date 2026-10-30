import pytest

from climateadapt.rag.chunking import ChunkingParams, chunk_document
from climateadapt.rag.citations import author_label, build_citation, format_pages, verify_citation
from climateadapt.rag.manifest import Manifest, SourceDocument
from climateadapt.rag.models import Page
from rag_helpers import make_chunk
from test_rag_manifest import valid_doc


def doc(**overrides):
    return SourceDocument.model_validate(valid_doc(**overrides))


@pytest.mark.parametrize(
    ("authors", "expected"),
    [
        ([], "Test Publisher"),
        (["Steduto, P."], "Steduto"),
        (["Nangia, V.", "Oweis, T."], "Nangia & Oweis"),
        (["Steduto, P.", "Hsiao, T.C.", "Fereres, E.", "Raes, D."], "Steduto et al."),
        (["Joint FAO/IAEA Division"], "Joint FAO/IAEA Division"),
    ],
)
def test_author_labels(authors, expected):
    assert author_label(doc(authors=authors)) == expected


def test_page_formatting():
    assert format_pages(7, 7) == "p. 7 (PDF index; no printed label)"
    assert format_pages(7, 9) == "pp. 7-9 (PDF index; no printed label)"
    assert format_pages(114, 114, "96", "96") == "PDF p. 114 (printed p. 96)"
    assert format_pages(3, 5, "1", "3") == "PDF pp. 3-5 (printed p. 1-3)"
    assert format_pages(3, 5, "1", None) == "PDF pp. 3-5 (printed p. 1)"


def test_formatted_citation_uses_only_manifest_fields():
    document = doc(
        authors=["Steduto, P.", "Hsiao, T.C.", "Fereres, E."],
        title="Crop yield response to water",
        series="FAO Irrigation and Drainage Paper 66",
        publisher="FAO",
        year=2012,
        unverified_fields=["year"],
    )
    citation = build_citation(
        make_chunk(3, "some text here", doc_id="test-doc-one", pages=(12, 13)),
        document,
    )

    assert citation.formatted == (
        "Steduto et al. (2012). Crop yield response to water. "
        "FAO Irrigation and Drainage Paper 66. FAO. pp. 12-13 (PDF index; no printed label)."
    )
    assert citation.pages == "pp. 12-13 (PDF index; no printed label)"
    assert citation.unverified_fields == ["year"]
    assert citation.license_status == "verified_in_record"
    assert citation.landing_url == "https://example.org/doc"


def test_missing_year_and_series_are_handled():
    citation = build_citation(
        make_chunk(0, "x y z", doc_id="test-doc-one"),
        doc(year=None, series=None),
    )
    assert citation.formatted.startswith(
        "Author (n.d.). A test document. Test Publisher. p. 1 (PDF index; no printed label)."
    )


def test_citing_a_chunk_with_the_wrong_document_is_an_error():
    with pytest.raises(ValueError):
        build_citation(make_chunk(0, "x y z", doc_id="other-doc"), doc())


def corpus():
    manifest = Manifest.model_validate(
        {"manifest_version": 1, "description": "x", "documents": [valid_doc()]}
    )
    pages = [
        Page(page=1, text="alpha beta gamma delta " * 20),
        Page(page=2, text="epsilon zeta " * 20),
    ]
    chunks, _ = chunk_document(
        "test-doc-one",
        pages,
        ChunkingParams(chunk_words=60, overlap_words=10, min_words=5),
    )
    return manifest, pages, chunks


def test_a_correct_citation_has_no_problems():
    manifest, pages, chunks = corpus()
    assert all(verify_citation(c, manifest, {"test-doc-one": pages}) == [] for c in chunks)


def test_citation_problems_are_reported():
    manifest, pages, chunks = corpus()
    pages_by_doc = {"test-doc-one": pages}

    unknown = chunks[0].model_copy(update={"doc_id": "ghost-doc"})
    assert "not in the manifest" in verify_citation(unknown, manifest, pages_by_doc)[0]
    assert "no stored pages" in verify_citation(chunks[0], manifest, {})[0]
    beyond = chunks[0].model_copy(update={"page_end": 99})
    assert "exceeds" in verify_citation(beyond, manifest, pages_by_doc)[0]
    wrong_text = chunks[0].model_copy(update={"text": chunks[0].text + " extra"})
    assert "does not re-derive" in verify_citation(wrong_text, manifest, pages_by_doc)[0]


def test_labeled_citations_show_both_page_numbers():
    citation = build_citation(
        make_chunk(0, "x y z", doc_id="test-doc-one", pages=(114, 114), labels=("96", "96")),
        doc(),
    )
    assert citation.pages == "PDF p. 114 (printed p. 96)"
    assert citation.formatted.endswith("PDF p. 114 (printed p. 96).")


def test_label_mismatches_are_reported():
    manifest, pages, chunks = corpus()
    labeled = [Page(page=1, text=pages[0].text, label="i"),
               Page(page=2, text=pages[1].text, label="ii")]
    chunk = chunks[0].model_copy(update={"label_start": "WRONG"})
    problems = verify_citation(chunk, manifest, {"test-doc-one": labeled})
    assert any("label_start" in p and "does not match" in p for p in problems)
    matching = chunks[0].model_copy(
        update={"label_start": "i", "label_end": labeled[chunks[0].page_end - 1].label}
    )
    assert verify_citation(matching, manifest, {"test-doc-one": labeled}) == []