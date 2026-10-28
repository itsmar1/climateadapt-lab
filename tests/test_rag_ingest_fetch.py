import json

import httpx
import pytest

from climateadapt.rag.chunking import ChunkingParams
from climateadapt.rag.fetch import FetchError, fetch_pdf, raw_pdf_path
from climateadapt.rag.ingest import (
    IngestError,
    extract_pages,
    ingest_document,
    load_chunks,
    load_pages,
    processed_doc_ids,
)
from climateadapt.rag.manifest import SourceDocument
from climateadapt.rag.text import words
from rag_helpers import make_pdf
from test_rag_manifest import valid_doc

PARAMS = ChunkingParams(chunk_words=40, overlap_words=10, min_words=10)


def document(**overrides):
    return SourceDocument.model_validate(valid_doc(**overrides))


def long_page(sentence, repeats=12):
    return "\n".join([sentence] * repeats)


# ---------------------------------------------------------------- extraction


def test_extract_pages_reads_text_per_page(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(make_pdf(["Alpha beta gamma.\nDelta epsilon.", "Zeta eta theta."]))

    pages, failed = extract_pages(pdf)

    assert [p.page for p in pages] == [1, 2]
    assert failed == []
    assert words(pages[0].text) == ["Alpha", "beta", "gamma.", "Delta", "epsilon."]
    assert words(pages[1].text) == ["Zeta", "eta", "theta."]


def test_pdfs_with_special_characters_are_extracted(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(make_pdf(["Rainfall (mm) and a back\\slash"]))
    pages, _ = extract_pages(pdf)
    assert words(pages[0].text) == ["Rainfall", "(mm)", "and", "a", "back\\slash"]


def test_unreadable_files_raise_ingest_error(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"<html>not a pdf</html>")
    with pytest.raises(IngestError, match="not a readable PDF"):
        extract_pages(pdf)


# ---------------------------------------------------------------- ingestion


def test_ingest_writes_outputs_that_reload_identically(tmp_path):
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    (raw / "test-doc-one.pdf").write_bytes(
        make_pdf([long_page("Supplemental irrigation stabilises rainfed wheat yields."),
                  long_page("Deficit irrigation saves water in cotton and maize.")])
    )

    report = ingest_document(document(), raw_dir=raw, processed_dir=processed, params=PARAMS)

    assert report.n_pages == 2
    assert report.empty_pages == [] and report.failed_pages == []
    assert report.n_chunks >= 3
    assert report.warnings == []
    chunks = load_chunks(processed)
    assert len(chunks) == report.n_chunks
    assert {c.doc_id for c in chunks} == {"test-doc-one"}
    assert len(load_pages(processed, "test-doc-one")) == 2
    assert processed_doc_ids(processed) == {"test-doc-one"}
    meta = json.loads((processed / "test-doc-one" / "meta.json").read_text(encoding="utf-8"))
    assert meta["pdf_sha256"] == report.pdf_sha256
    assert meta["chunking_params"]["chunk_words"] == 40


def test_scanned_style_pdfs_produce_a_warning(tmp_path):
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    (raw / "test-doc-one.pdf").write_bytes(make_pdf(["", "", "A single caption line"]))

    report = ingest_document(document(), raw_dir=raw, processed_dir=processed, params=PARAMS)

    assert report.empty_pages == [1, 2]
    assert any("scanned" in w for w in report.warnings)
    assert any("No chunks" in w for w in report.warnings)


def test_missing_pdf_explains_where_to_get_it(tmp_path):
    with pytest.raises(IngestError, match="https://example.org/doc"):
        ingest_document(document(), raw_dir=tmp_path, processed_dir=tmp_path / "p", params=PARAMS)


# ---------------------------------------------------------------- fetching


def client_for(routes):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        route = routes.get(str(request.url))
        if route is None:
            return httpx.Response(404)
        if callable(route):
            return route()
        return httpx.Response(200, content=route, headers={"content-type": "application/pdf"})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_fetch_downloads_verifies_and_records_the_source(tmp_path):
    pdf_bytes = make_pdf(["Hello"])
    client, calls = client_for({"https://example.org/doc.pdf": pdf_bytes})

    result = fetch_pdf(document(), tmp_path, client)

    target = raw_pdf_path(tmp_path, "test-doc-one")
    assert target.read_bytes() == pdf_bytes
    assert result.size_bytes == len(pdf_bytes) and not result.skipped_existing
    sidecar = json.loads((tmp_path / "test-doc-one.source.json").read_text(encoding="utf-8"))
    assert sidecar["requested_url"] == "https://example.org/doc.pdf"
    assert sidecar["sha256"] == result.sha256
    assert len(calls) == 1

    again = fetch_pdf(document(), tmp_path, client)
    assert again.skipped_existing and len(calls) == 1
    forced = fetch_pdf(document(), tmp_path, client, force=True)
    assert not forced.skipped_existing and len(calls) == 2


def test_fetch_falls_back_to_the_next_candidate_url(tmp_path):
    doc = document(pdf_urls=["https://a.example.org/x.pdf", "https://b.example.org/x.pdf"])
    client, calls = client_for(
        {
            "https://a.example.org/x.pdf": b"<html>login required</html>",
            "https://b.example.org/x.pdf": make_pdf(["ok"]),
        }
    )

    result = fetch_pdf(doc, tmp_path, client)

    assert result.source_url == "https://b.example.org/x.pdf"
    assert len(calls) == 2


def test_fetch_reports_every_failure_and_leaves_no_files(tmp_path):
    doc = document(pdf_urls=["https://a.example.org/x.pdf", "https://b.example.org/x.pdf"])
    client, _ = client_for({"https://a.example.org/x.pdf": b"<html>no</html>"})

    with pytest.raises(FetchError, match="not a PDF.*HTTP 404"):
        fetch_pdf(doc, tmp_path, client)
    assert list(tmp_path.iterdir()) == []


def test_fetch_enforces_the_size_limit(tmp_path):
    client, _ = client_for({"https://example.org/doc.pdf": make_pdf(["x " * 500])})
    with pytest.raises(FetchError, match="limit"):
        fetch_pdf(document(), tmp_path, client, max_bytes=100)
    assert list(tmp_path.iterdir()) == []


def test_network_errors_are_reported(tmp_path):
    def boom():
        raise httpx.ConnectError("no route")

    client, _ = client_for({"https://example.org/doc.pdf": boom})
    with pytest.raises(FetchError, match="network error"):
        fetch_pdf(document(), tmp_path, client)


def test_manual_documents_are_not_fetched(tmp_path):
    client, calls = client_for({})
    with pytest.raises(FetchError, match="manual download"):
        fetch_pdf(document(access="manual", pdf_urls=[]), tmp_path, client)
    assert calls == []