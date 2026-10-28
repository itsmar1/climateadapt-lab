"""PDF text extraction and corpus ingestion (raw PDF -> pages.jsonl, chunks.jsonl, meta.json).

No OCR: a scanned PDF yields empty pages, which is reported as a warning, never hidden.
Processed text stays under data/corpus/ (git-ignored); only the manifest is committed.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from climateadapt.rag.chunking import DEFAULT_CHUNKING_PARAMS, ChunkingParams, chunk_document
from climateadapt.rag.manifest import SourceDocument
from climateadapt.rag.models import Chunk, Page
from climateadapt.rag.text import normalize_text

logger = logging.getLogger(__name__)

EMPTY_PAGE_WARNING_RATIO = 0.5


class IngestError(Exception):
    """A document could not be extracted or is missing."""


class IngestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    pdf_sha256: str
    pdf_size_bytes: int
    n_pages: int
    empty_pages: list[int]
    failed_pages: list[int]
    n_words: int
    n_chunks: int
    n_dropped_short: int
    n_dropped_low_alpha: int
    warnings: list[str]


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def extract_pages(pdf_path: Path) -> tuple[list[Page], list[int]]:
    """Extract text per page. Returns (pages, page numbers whose extraction failed)."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestError(f"{pdf_path.name} is encrypted and needs a password.")
        page_objects = list(reader.pages)
    except (PyPdfError, OSError, ValueError) as exc:
        raise IngestError(f"{pdf_path.name} is not a readable PDF: {exc}") from exc

    pages: list[Page] = []
    failed: list[int] = []
    for number, page_object in enumerate(page_objects, start=1):
        try:
            text = page_object.extract_text() or ""
        except Exception as exc:  # third-party boundary: pypdf raises many error types
            logger.warning(
                "Text extraction failed on page %d of %s: %s",
                number,
                pdf_path.name,
                exc,
            )
            text, failed = "", [*failed, number]
        pages.append(Page(page=number, text=text))
    return pages, failed


def _write_jsonl(path: Path, items: Iterable[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(item.model_dump_json() + "\n")
    os.replace(tmp, path)


def _read_jsonl(path: Path, model: type[BaseModel]) -> list:
    with open(path, encoding="utf-8") as handle:
        return [model.model_validate_json(line) for line in handle if line.strip()]


def ingest_document(
    doc: SourceDocument,
    *,
    raw_dir: Path,
    processed_dir: Path,
    params: ChunkingParams = DEFAULT_CHUNKING_PARAMS,
) -> IngestReport:
    pdf_path = raw_dir / f"{doc.doc_id}.pdf"
    if not pdf_path.exists():
        raise IngestError(
            f"No PDF for {doc.doc_id}: expected {pdf_path}. "
            f"Download it from {doc.landing_url} (see corpus/manifest.json)."
        )
    sha, size = sha256_file(pdf_path)
    pages, failed = extract_pages(pdf_path)
    chunks, stats = chunk_document(doc.doc_id, pages, params)
    empty = [page.page for page in pages if not normalize_text(page.text)]

    warnings: list[str] = []
    if pages and len(empty) / len(pages) > EMPTY_PAGE_WARNING_RATIO:
        warnings.append(
            f"{len(empty)} of {len(pages)} pages have no extractable text; the PDF may be "
            "scanned. OCR is not implemented, so this document will be poorly searchable."
        )
    if failed:
        warnings.append(f"Text extraction raised errors on pages {failed}.")
    if not chunks:
        warnings.append("No chunks were produced for this document.")

    out_dir = processed_dir / doc.doc_id
    _write_jsonl(out_dir / "pages.jsonl", pages)
    _write_jsonl(out_dir / "chunks.jsonl", chunks)
    import pypdf

    meta = {
        "doc_id": doc.doc_id,
        "pdf_sha256": sha,
        "pdf_size_bytes": size,
        "pypdf_version": pypdf.__version__,
        "chunking_params": asdict(params),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "n_pages": stats.n_pages,
        "n_chunks": stats.n_chunks_kept,
    }
    import json

    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return IngestReport(
        doc_id=doc.doc_id,
        pdf_sha256=sha,
        pdf_size_bytes=size,
        n_pages=stats.n_pages,
        empty_pages=empty,
        failed_pages=failed,
        n_words=stats.n_words,
        n_chunks=stats.n_chunks_kept,
        n_dropped_short=stats.n_chunks_dropped_short,
        n_dropped_low_alpha=stats.n_chunks_dropped_low_alpha,
        warnings=warnings,
    )


def load_pages(processed_dir: Path, doc_id: str) -> list[Page]:
    return _read_jsonl(processed_dir / doc_id / "pages.jsonl", Page)


def load_chunks(processed_dir: Path, doc_ids: Iterable[str] | None = None) -> list[Chunk]:
    """Load chunks of the given documents (default: every processed document), in id order."""
    if doc_ids is None:
        doc_ids = sorted(p.name for p in processed_dir.iterdir() if (p / "chunks.jsonl").exists())
    chunks: list[Chunk] = []
    for doc_id in doc_ids:
        path = processed_dir / doc_id / "chunks.jsonl"
        if path.exists():
            chunks.extend(_read_jsonl(path, Chunk))
    return chunks


def processed_doc_ids(processed_dir: Path) -> set[str]:
    if not processed_dir.exists():
        return set()
    return {p.name for p in processed_dir.iterdir() if (p / "chunks.jsonl").exists()}