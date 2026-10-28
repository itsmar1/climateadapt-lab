from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from climateadapt.rag.evaluation import load_eval_set
from climateadapt.rag.manifest import Manifest, SourceDocument, load_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "corpus" / "manifest.json"
EVAL_SET = ROOT / "corpus" / "eval" / "queries.json"


def valid_doc(**overrides):
    doc = {
        "doc_id": "test-doc-one",
        "title": "A test document",
        "authors": ["Author, A."],
        "publisher": "Test Publisher",
        "year": 2020,
        "series": None,
        "identifier": None,
        "source_type": "technical_report",
        "language": "en",
        "topics": ["testing"],
        "regions": [],
        "landing_url": "https://example.org/doc",
        "pdf_urls": ["https://example.org/doc.pdf"],
        "access": "automatic",
        "license": "CC-BY-4.0",
        "license_status": "verified_in_record",
        "license_notes": None,
        "unverified_fields": [],
        "verification_notes": "Verified against the publisher record.",
        "metadata_verified_on": "2026-10-28",
    }
    doc.update(overrides)
    return doc


def test_the_real_manifest_is_valid():
    manifest = load_manifest(MANIFEST)

    assert len(manifest.documents) >= 6
    assert len(set(manifest.doc_ids)) == len(manifest.documents)
    publishers = {d.publisher for d in manifest.documents}
    assert {"FAO", "ICARDA"} <= publishers
    for doc in manifest.documents:
        assert doc.metadata_verified_on <= date(2030, 1, 1)
        if doc.license_status == "unverified":
            assert "license" in doc.unverified_fields


def test_the_real_eval_set_matches_the_manifest():
    manifest = load_manifest(MANIFEST)
    eval_set = load_eval_set(EVAL_SET, manifest)

    assert len(eval_set.queries) >= 10
    assert {q.language for q in eval_set.queries} >= {"en", "fr", "ar"}
    assert all(q.relevance_basis for q in eval_set.queries)


def test_unknown_document_in_the_eval_set_is_rejected(tmp_path):
    manifest = load_manifest(MANIFEST)
    path = tmp_path / "queries.json"
    path.write_text(
        '{"eval_version": 1, "description": "x", "queries": [{"id": "q1", "query": "water use", '
        '"relevant_doc_ids": ["does-not-exist"], "relevance_basis": "invented"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not in the manifest"):
        load_eval_set(path, manifest)


def test_a_valid_document_parses():
    doc = SourceDocument.model_validate(valid_doc())
    assert doc.metadata_verified_on == date(2026, 10, 28)


@pytest.mark.parametrize(
    "overrides",
    [
        {"doc_id": "Bad_ID"},
        {"doc_id": "ab"},
        {"landing_url": "ftp://example.org/x"},
        {"pdf_urls": ["not a url"]},
        {"access": "automatic", "pdf_urls": []},
        {"unverified_fields": ["colour"]},
        {"source_type": "blog"},
        {"language": "english"},
        {"year": 1800},
        {"unexpected": 1},
    ],
)
def test_invalid_documents_are_rejected(overrides):
    with pytest.raises(ValidationError):
        SourceDocument.model_validate(valid_doc(**overrides))


def test_manual_documents_may_have_no_pdf_urls():
    doc = SourceDocument.model_validate(valid_doc(access="manual", pdf_urls=[]))
    assert doc.access == "manual"


def test_duplicate_doc_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate doc_id"):
        Manifest.model_validate(
            {"manifest_version": 1, "description": "x", "documents": [valid_doc(), valid_doc()]}
        )


def test_lookup_by_id():
    manifest = Manifest.model_validate(
        {"manifest_version": 1, "description": "x", "documents": [valid_doc()]}
    )
    assert manifest.get("test-doc-one").title == "A test document"
    with pytest.raises(KeyError):
        manifest.get("nope")