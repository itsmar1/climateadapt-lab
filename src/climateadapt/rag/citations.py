"""Citations built only from verified manifest metadata and a chunk's own page range."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from climateadapt.rag.chunking import verify_chunk_provenance
from climateadapt.rag.manifest import Manifest, SourceDocument
from climateadapt.rag.models import Chunk, Page


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    title: str
    authors: list[str]
    publisher: str
    year: int | None
    series: str | None
    identifier: str | None
    pages: str
    landing_url: str
    license: str
    license_status: str
    unverified_fields: list[str]
    formatted: str


def format_pages(start: int, end: int) -> str:
    return f"p. {start}" if start == end else f"pp. {start}-{end}"


def _surname(author: str) -> str:
    return author.split(",")[0].strip()


def author_label(doc: SourceDocument) -> str:
    if not doc.authors:
        return doc.publisher
    names = [_surname(a) for a in doc.authors]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return f"{names[0]} et al."


def build_citation(chunk: Chunk, doc: SourceDocument) -> Citation:
    if chunk.doc_id != doc.doc_id:
        raise ValueError(f"Chunk belongs to {chunk.doc_id!r}, not {doc.doc_id!r}.")
    pages = format_pages(chunk.page_start, chunk.page_end)
    year = str(doc.year) if doc.year is not None else "n.d."
    series = f"{doc.series}. " if doc.series else ""
    formatted = f"{author_label(doc)} ({year}). {doc.title}. {series}{doc.publisher}. {pages}."
    return Citation(
        chunk_id=chunk.chunk_id,
        doc_id=doc.doc_id,
        title=doc.title,
        authors=list(doc.authors),
        publisher=doc.publisher,
        year=doc.year,
        series=doc.series,
        identifier=doc.identifier,
        pages=pages,
        landing_url=doc.landing_url,
        license=doc.license,
        license_status=doc.license_status,
        unverified_fields=list(doc.unverified_fields),
        formatted=formatted,
    )


def verify_citation(
    chunk: Chunk, manifest: Manifest, pages_by_doc: Mapping[str, Sequence[Page]]
) -> list[str]:
    """Return a list of problems (empty means the citation is correct and traceable)."""
    problems: list[str] = []
    try:
        manifest.get(chunk.doc_id)
    except KeyError:
        return [f"{chunk.chunk_id}: document {chunk.doc_id!r} is not in the manifest."]
    pages = pages_by_doc.get(chunk.doc_id)
    if pages is None:
        return [f"{chunk.chunk_id}: no stored pages for {chunk.doc_id!r}."]
    if chunk.page_end > len(pages):
        problems.append(
            f"{chunk.chunk_id}: page_end {chunk.page_end} exceeds "
            f"the document's {len(pages)} pages."
        )
    elif not verify_chunk_provenance(chunk, pages):
        problems.append(f"{chunk.chunk_id}: text does not re-derive from pages "
                        f"{chunk.page_start}-{chunk.page_end}.")
    return problems