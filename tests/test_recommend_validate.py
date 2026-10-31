"""Validator tests: traceability errors, warnings, and offline behavior."""

from __future__ import annotations

from climateadapt.recommend.validate import IngestedDocInfo, validate_catalog
from recommend_helpers import make_catalog, make_entry, make_manifest


def _messages(report, level: str) -> list[str]:
    issues = report.errors if level == "error" else report.warnings
    return [issue.message for issue in issues]


def test_valid_catalog_passes():
    report = validate_catalog(
        make_catalog(make_entry()),
        make_manifest("test-doc-one"),
        {"test-doc-one": IngestedDocInfo(n_pages=10)},
    )
    assert report.ok
    assert report.errors == []
    assert report.warnings == []
    assert report.checked_entries == 1


def test_evidence_doc_missing_from_manifest_is_an_error():
    report = validate_catalog(
        make_catalog(make_entry()),
        make_manifest("other-doc"),
        {"test-doc-one": IngestedDocInfo(n_pages=10)},
    )
    assert not report.ok
    assert any("not in the manifest" in m for m in _messages(report, "error"))


def test_supported_link_to_non_ingested_doc_is_an_error():
    report = validate_catalog(
        make_catalog(make_entry()),
        make_manifest("test-doc-one"),
        {"other-doc": IngestedDocInfo(n_pages=10)},
    )
    assert not report.ok
    assert any("not ingested" in m for m in _messages(report, "error"))


def test_page_beyond_the_ingested_range_is_an_error():
    report = validate_catalog(
        make_catalog(make_entry()),
        make_manifest("test-doc-one"),
        {"test-doc-one": IngestedDocInfo(n_pages=2)},
    )
    assert not report.ok
    assert any("exceeds the 2 ingested pages" in m for m in _messages(report, "error"))


def test_empty_evidence_page_is_a_warning():
    report = validate_catalog(
        make_catalog(make_entry()),
        make_manifest("test-doc-one"),
        {"test-doc-one": IngestedDocInfo(n_pages=10, empty_pages=frozenset({3}))},
    )
    assert report.ok
    assert any("no extractable text" in m for m in _messages(report, "warning"))


def test_unknown_expected_source_is_an_error():
    entry = make_entry(
        evidence_status="needs_evidence",
        evidence_links=[],
        expected_sources=["ghost-doc"],
        needs_evidence_note="Supporting document is not ingested yet.",
    )
    report = validate_catalog(
        make_catalog(entry), make_manifest("test-doc-one"),
        {"test-doc-one": IngestedDocInfo(n_pages=10)},
    )
    assert not report.ok
    assert any("not in the manifest" in m for m in _messages(report, "error"))


def test_newly_ingested_expected_source_is_a_warning():
    entry = make_entry(
        evidence_status="needs_evidence",
        evidence_links=[],
        expected_sources=["test-doc-one"],
        needs_evidence_note="Supporting document is not ingested yet.",
    )
    report = validate_catalog(
        make_catalog(entry), make_manifest("test-doc-one"),
        {"test-doc-one": IngestedDocInfo(n_pages=10)},
    )
    assert report.ok
    assert any("upgradable" in m for m in _messages(report, "warning"))


def test_quantitative_description_is_flagged_for_review():
    entry = make_entry(description="Cuts water use by 30 % in every season, always.")
    report = validate_catalog(
        make_catalog(entry), make_manifest("test-doc-one"),
        {"test-doc-one": IngestedDocInfo(n_pages=10)},
    )
    assert report.ok
    assert any("quantitative expression" in m for m in _messages(report, "warning"))


def test_cited_doc_with_unverified_fields_is_flagged():
    manifest = make_manifest("test-doc-one")
    manifest.documents[0].unverified_fields.append("year")
    report = validate_catalog(
        make_catalog(make_entry()), manifest,
        {"test-doc-one": IngestedDocInfo(n_pages=10)},
    )
    assert report.ok
    assert any("unverified manifest fields" in m for m in _messages(report, "warning"))


def test_missing_corpus_info_skips_ingest_checks_but_keeps_manifest_checks():
    report = validate_catalog(make_catalog(make_entry()), make_manifest("test-doc-one"), None)
    assert report.ok
    assert any("checks skipped" in m for m in _messages(report, "warning"))

    report = validate_catalog(make_catalog(make_entry()), make_manifest("other-doc"), None)
    assert not report.ok
    assert any("not in the manifest" in m for m in _messages(report, "error"))
