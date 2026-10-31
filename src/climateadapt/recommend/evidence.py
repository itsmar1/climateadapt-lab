"""Evidence-strength rubric and evidence-reference formatting.

Rubric (count-based, deterministic; documented in docs/RECOMMENDATION_ENGINE.md):

* level 0 ``needs_evidence`` — the entry is marked ``needs_evidence`` or has no
  resolvable evidence link. The entry is excluded from ranking.
* level 1 ``single_source`` — at least one resolvable link, all in one document.
* level 2 ``multi_source`` — resolvable links spanning at least two documents.

A link is resolvable when its document is ingested (present in the
``ingested_doc_ids`` set) or, when no ingested set is supplied, when the entry
is marked ``supported``. Normalized score = level / MAX_EVIDENCE_LEVEL.

The rubric counts traceable links only; it says nothing about study quality or
effect sizes, which the catalog never claims.
"""

from __future__ import annotations

from climateadapt.rag.citations import author_label, format_pages
from climateadapt.rag.manifest import Manifest
from climateadapt.recommend.schema import (
    EvidenceLink,
    EvidenceReference,
    Intervention,
)

LEVEL_NEEDS_EVIDENCE = 0
LEVEL_SINGLE_SOURCE = 1
LEVEL_MULTI_SOURCE = 2
MAX_EVIDENCE_LEVEL = 2

LEVEL_NAMES = {
    LEVEL_NEEDS_EVIDENCE: "needs_evidence",
    LEVEL_SINGLE_SOURCE: "single_source",
    LEVEL_MULTI_SOURCE: "multi_source",
}


def resolvable_links(
    entry: Intervention, ingested_doc_ids: set[str] | None = None
) -> list[EvidenceLink]:
    """Evidence links whose document counts as ingested (in catalog order)."""
    if entry.evidence_status != "supported":
        return []
    if ingested_doc_ids is None:
        return list(entry.evidence_links)
    return [link for link in entry.evidence_links if link.doc_id in ingested_doc_ids]


def evidence_level(
    entry: Intervention, ingested_doc_ids: set[str] | None = None
) -> int:
    """Rubric level (0-2) for one entry."""
    docs = {link.doc_id for link in resolvable_links(entry, ingested_doc_ids)}
    if not docs:
        return LEVEL_NEEDS_EVIDENCE
    if len(docs) >= 2:
        return LEVEL_MULTI_SOURCE
    return LEVEL_SINGLE_SOURCE


def evidence_score(
    entry: Intervention, ingested_doc_ids: set[str] | None = None
) -> float:
    """Normalized rubric score in {0.0, 0.5, 1.0}."""
    return evidence_level(entry, ingested_doc_ids) / MAX_EVIDENCE_LEVEL


def format_evidence_reference(link: EvidenceLink, manifest: Manifest) -> EvidenceReference:
    """Resolve one link against the manifest (raises KeyError when absent).

    Every field comes from the manifest or the link itself; nothing is invented.
    """
    doc = manifest.get(link.doc_id)
    year = str(doc.year) if doc.year is not None else "n.d."
    series = f"{doc.series}. " if doc.series else ""
    pages = format_pages(link.pdf_page, link.pdf_page)
    citation = f"{author_label(doc)} ({year}). {doc.title}. {series}{doc.publisher}. {pages}."
    return EvidenceReference(
        doc_id=doc.doc_id,
        pdf_page=link.pdf_page,
        reference=link.reference,
        citation=citation,
        landing_url=doc.landing_url,
        license=doc.license,
        license_status=doc.license_status,
        unverified_fields=list(doc.unverified_fields),
    )
