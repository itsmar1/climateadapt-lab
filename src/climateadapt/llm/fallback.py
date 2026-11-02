"""Deterministic fallback report. No LLM, no narrative, no invented values.

``build_fallback_report`` renders the bundle, the ranking, and the retrieved
citations into a :class:`~climateadapt.llm.report.Report` with fixed templates.
Every numeral is copied from the registry, every citation is rebuilt from the
manifest, and the report is labelled ``deterministic-fallback`` so the UI can
banner it. It must always pass :func:`validate_report` with
``allow_fallback=True`` — the tests pin that.
"""

from __future__ import annotations

from typing import Any

from climateadapt.llm.composite import statement_locations
from climateadapt.llm.report import (
    FALLBACK_GENERATOR,
    EvidenceItem,
    ExcludedOption,
    RankedRecommendation,
    Report,
    ReportedNumber,
    Statement,
    ToolOutputRegistry,
    build_registry,
    constraints_output_id,
    ranking_output_id,
)
from climateadapt.rag.citations import build_citation
from climateadapt.rag.manifest import Manifest
from climateadapt.rag.models import Chunk

MAX_NOTE_CODES = 6


def _render(value: float) -> str:
    return str(int(value)) if value.is_integer() else repr(value)


def _as_dict(model_or_dict: Any) -> dict[str, Any]:
    return (
        model_or_dict.model_dump(mode="json")
        if hasattr(model_or_dict, "model_dump")
        else model_or_dict
    )


def _number(
    registry: ToolOutputRegistry, output_id: str, field: str, unit: str | None = None
) -> ReportedNumber | None:
    value = registry.lookup_number(output_id, field)
    if value is None:
        return None
    return ReportedNumber(
        value=value, unit=unit, tool_output_id=output_id, field=field
    )


def _finding_text(
    indicator: str, entry: dict[str, Any], registry: ToolOutputRegistry
) -> tuple[str, list[ReportedNumber]]:
    status = entry.get("status", "failed")
    result = entry.get("result") or {}
    if status not in ("ok", "undefined") or not result:
        text = f"{indicator}: status {status}; no values computed"
        if entry.get("error_type"):
            text += f" ({entry['error_type']})"
        return text + ".", []
    output = registry.outputs[indicator]
    parts: list[str] = []
    numbers: list[ReportedNumber] = []
    for field_name in sorted(output.values):
        number = _number(registry, indicator, field_name)
        assert number is not None
        numbers.append(number)
        parts.append(f"{field_name} {_render(number.value)}")
    source = output.texts.get("data_source", "")
    head = f"{indicator} ({source})" if source else indicator
    return f"{head}: status {status}. " + "; ".join(parts) + ".", numbers


def _matching_chunks(
    doc_id: str, pdf_page: int, chunks: list[Chunk]
) -> list[str]:
    return [
        chunk.chunk_id
        for chunk in chunks
        if chunk.doc_id == doc_id and chunk.page_start <= pdf_page <= chunk.page_end
    ]


def _note(problems: list[str]) -> str:
    codes: list[str] = []
    for problem in problems:
        if not problem.startswith("[") or "]" not in problem:
            code = "unspecified"
        else:
            code = problem[1:].split("]", 1)[0]
        if code and code not in codes:
            codes.append(code)
    shown = ", ".join(codes[:MAX_NOTE_CODES])
    if len(codes) > MAX_NOTE_CODES:
        shown += " and others"
    return f"Model output rejected ({shown}); deterministic values only."


def build_fallback_report(
    bundle: Any,
    recommendations: Any,
    chunks: list[Chunk],
    manifest: Manifest,
    problems: list[str],
) -> Report:
    """Render bundle + ranking + citations with fixed templates (no AI text)."""
    data = _as_dict(bundle)
    ranking = _as_dict(recommendations)
    registry = build_registry(bundle, recommendations)

    findings: list[Statement] = []
    for entry in data.get("entries", []):
        text, numbers = _finding_text(entry["indicator"], entry, registry)
        findings.append(
            Statement(
                text=text,
                tool_output_ids=[entry["indicator"]],
                numbers=numbers,
            )
        )

    evidence: list[EvidenceItem] = []
    for chunk in chunks:
        try:
            citation = build_citation(chunk, manifest.get(chunk.doc_id))
        except (KeyError, ValueError):
            continue
        evidence.append(
            EvidenceItem(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                citation=citation.formatted,
                pages=citation.pages,
                landing_url=citation.landing_url,
                license=citation.license,
                license_status=citation.license_status,
            )
        )

    ranked: list[RankedRecommendation] = []
    for option in ranking.get("ranked", []):
        output_id = ranking_output_id(option["intervention_id"])
        numbers = [
            n
            for field_name in ("score_total", *sorted(option["score_components"]))
            if (n := _number(registry, output_id, field_name)) is not None
        ]
        score = registry.lookup_number(output_id, "score_total")
        assert score is not None
        evidence_ids: list[str] = []
        for link in option.get("evidence", []):
            for chunk_id in _matching_chunks(link["doc_id"], link["pdf_page"], chunks):
                if chunk_id not in evidence_ids:
                    evidence_ids.append(chunk_id)
        ranked.append(
            RankedRecommendation(
                intervention_id=option["intervention_id"],
                name=option["name"],
                benefit=option["benefit"],
                cost=option["cost"],
                risk=option["risk"],
                narrative=Statement(
                    text=(
                        f"{option['name']} ({option['intervention_id']}): "
                        f"ranked with score {_render(score)}. "
                        "Benefit, cost and risk are stated in the catalog entry."
                    ),
                    evidence_ids=evidence_ids,
                    tool_output_ids=[output_id],
                    numbers=numbers,
                ),
            )
        )

    excluded: list[ExcludedOption] = []
    for option in ranking.get("excluded", []):
        codes = [reason["code"] for reason in option["reasons"]]
        excluded.append(
            ExcludedOption(
                intervention_id=option["intervention_id"],
                name=option["name"],
                reason_codes=codes,
                narrative=Statement(
                    text=(
                        f"{option['name']} ({option['intervention_id']}): excluded. "
                        f"Reasons: {', '.join(codes)}."
                    ),
                    tool_output_ids=[constraints_output_id(option["intervention_id"])],
                ),
            )
        )

    limitations = [
        "Deterministic fallback report: values are copied from tool outputs; "
        "no AI narrative is included.",
        "Indicator values are reported without drought categories or composite scores.",
        "Benefit, cost and risk are unknown unless the catalog cites a source.",
        "Reference years with incomplete data were excluded, not imputed.",
    ]
    for entry in data.get("entries", []):
        if entry.get("status") == "failed" and entry.get("error_type"):
            limitations.append(
                f"Indicator {entry['indicator']} failed ({entry['error_type']}); "
                "its values are absent, not zero."
            )

    lat = registry.lookup_number("bundle", "latitude")
    lon = registry.lookup_number("bundle", "longitude")
    timescale = registry.lookup_number("bundle", "timescale_months")
    start_year = registry.lookup_number("bundle", "reference_start_year")
    end_year = registry.lookup_number("bundle", "reference_end_year")
    assert None not in (lat, lon, timescale, start_year, end_year)
    coverage_numbers = [
        n
        for field_name in (
            "latitude", "longitude", "timescale_months",
            "reference_start_year", "reference_end_year",
        )
        if (n := _number(registry, "bundle", field_name)) is not None
    ]
    coverage = Statement(
        text=(
            f"Location {_render(lat or 0.0)}, {_render(lon or 0.0)}; target window "
            f"ending {data['target_end_month']}; timescale {_render(timescale or 0.0)} "
            f"months; reference {_render(start_year or 0.0)} to {_render(end_year or 0.0)}."
        ),
        tool_output_ids=["bundle"],
        numbers=coverage_numbers,
    )

    provenance_refs = ["bundle"]
    provenance_refs.extend(entry["indicator"] for entry in data.get("entries", []))
    provenance_refs.extend(
        ranking_output_id(o["intervention_id"]) for o in ranking.get("ranked", [])
    )
    provenance_refs.extend(
        constraints_output_id(o["intervention_id"]) for o in ranking.get("excluded", [])
    )

    report = Report(
        generator=FALLBACK_GENERATOR,
        fallback=True,
        fallback_note=_note(problems),
        summary=Statement(
            text="Deterministic fallback report: bundle and ranking results are "
            "reproduced below without AI interpretation.",
            tool_output_ids=["bundle"],
        ),
        environmental_findings=findings,
        evidence=evidence,
        ranked_recommendations=ranked,
        excluded_options=excluded,
        limitations=limitations,
        assumptions=[
            "No AI interpretation was applied; all values are deterministic outputs.",
            "Retrieved passages are cited for traceability, not quoted as advice.",
        ],
        data_coverage=coverage,
        provenance_refs=provenance_refs,
        acceptance="fallback",
    )
    return report.model_copy(
        update={
            "statement_origins": {
                location: "platform" for location in statement_locations(report)
            }
        }
    )
