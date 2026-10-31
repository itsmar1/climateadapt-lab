"""Catalog validation against the manifest and the ingested corpus (offline).

Checks traceability (every ``doc_id``/page exists), status consistency
(``supported`` entries link to ingested documents; ``needs_evidence`` entries
link nowhere), and flags quantitative expressions in free text for human
review. Semantic support — whether a page really backs an entry — is NOT
checkable here and stays an owner-review item.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from climateadapt.rag.manifest import Manifest
from climateadapt.recommend.schema import InterventionCatalog

QUANTITATIVE_CLAIM_PATTERN = re.compile(
    r"\d\s*%|\b\d+(?:\.\d+)?\s*(?:t/ha|kg/ha|tonnes?/ha|percent|percentage)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IngestedDocInfo:
    """Ingested-document facts the validator needs (no text content)."""

    n_pages: int
    empty_pages: frozenset[int] = frozenset()


@dataclass(frozen=True)
class ValidationIssue:
    """One finding (``entry`` is None for catalog-wide findings)."""

    level: Literal["error", "warning"]
    entry: str | None
    message: str


@dataclass
class ValidationReport:
    """Validator outcome: ``ok`` is True when no errors were found."""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    checked_entries: int = 0

    @property
    def ok(self) -> bool:
        """Whether validation passed (warnings do not fail)."""
        return not self.errors


def validate_catalog(
    catalog: InterventionCatalog,
    manifest: Manifest,
    ingested: dict[str, IngestedDocInfo] | None,
) -> ValidationReport:
    """Validate one catalog. ``ingested=None`` skips page-range/ingest checks."""
    report = ValidationReport(checked_entries=len(catalog.interventions))
    if ingested is None:
        report.warnings.append(
            ValidationIssue(
                level="warning",
                entry=None,
                message="No ingested-corpus info: page-range and ingest checks skipped.",
            )
        )
    known_docs = set(manifest.doc_ids)
    for entry in catalog.interventions:
        for link in entry.evidence_links:
            if link.doc_id not in known_docs:
                report.errors.append(
                    ValidationIssue(
                        level="error",
                        entry=entry.intervention_id,
                        message=f"Evidence doc_id {link.doc_id!r} is not in the manifest.",
                    )
                )
                continue
            if ingested is None:
                continue
            info = ingested.get(link.doc_id)
            if info is None:
                report.errors.append(
                    ValidationIssue(
                        level="error",
                        entry=entry.intervention_id,
                        message=(
                            f"Evidence doc_id {link.doc_id!r} is not ingested; "
                            "'supported' entries must link to ingested documents."
                        ),
                    )
                )
            elif link.pdf_page > info.n_pages:
                report.errors.append(
                    ValidationIssue(
                        level="error",
                        entry=entry.intervention_id,
                        message=(
                            f"PDF page {link.pdf_page} exceeds the {info.n_pages} "
                            f"ingested pages of {link.doc_id!r}."
                        ),
                    )
                )
            elif link.pdf_page in info.empty_pages:
                report.warnings.append(
                    ValidationIssue(
                        level="warning",
                        entry=entry.intervention_id,
                        message=(
                            f"PDF page {link.pdf_page} of {link.doc_id!r} has no "
                            "extractable text."
                        ),
                    )
                )
        for source in entry.expected_sources:
            if source not in known_docs:
                report.errors.append(
                    ValidationIssue(
                        level="error",
                        entry=entry.intervention_id,
                        message=f"Expected source {source!r} is not in the manifest.",
                    )
                )
            elif ingested is not None and source in ingested:
                report.warnings.append(
                    ValidationIssue(
                        level="warning",
                        entry=entry.intervention_id,
                        message=(
                            f"Expected source {source!r} is now ingested; "
                            "the entry may be upgradable to 'supported'."
                        ),
                    )
                )
        if QUANTITATIVE_CLAIM_PATTERN.search(entry.description):
            report.warnings.append(
                ValidationIssue(
                    level="warning",
                    entry=entry.intervention_id,
                    message="Description holds a quantitative expression; figures need "
                    "a cited benefit/cost/risk statement or removal.",
                )
            )
        for cited in {link.doc_id for link in entry.evidence_links} & known_docs:
            unverified = manifest.get(cited).unverified_fields
            if unverified:
                report.warnings.append(
                    ValidationIssue(
                        level="warning",
                        entry=entry.intervention_id,
                        message=f"Cited document {cited!r} has unverified manifest "
                        f"fields: {', '.join(unverified)}.",
                    )
                )
    return report
