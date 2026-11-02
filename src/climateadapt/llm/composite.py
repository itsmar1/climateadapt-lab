"""Statement-level acceptance: keep valid model statements, replace the rest.

P23 (owner-approved design change for KI-35). One bad sentence no longer
discards an otherwise valid model report — but nothing reaches a user that the
unchanged validator has not accepted as a whole:

* :func:`group_by_statement` sorts validator problems by the statement
  location they already carry (``environmental_findings[3]``,
  ``limitations[2]``, ...). Problems with no statement location (missing
  section, schema failure, citation-set failure, bad refs) force the full
  deterministic fallback.
* :func:`build_composite` keeps every model statement with no problems and
  replaces each failing statement with the deterministic fallback's
  counterpart (matched by section plus indicator id / intervention id / chunk
  id / position). A failing statement with no safe counterpart is dropped.
* The caller MUST re-validate the composite with the unchanged validator and
  ship the full fallback on any problem. Cascades (a kept statement citing a
  dropped entry) are caught there, by construction.

Locations use the validator's path vocabulary so trace verdicts, report
fields, and UI labels all name the same statements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from climateadapt.llm.report import Report

Origin = Literal["model", "platform"]
"""Authorship of one counted statement."""

_STATEMENT_PATH_RE = re.compile(
    r"^(?:(?P<single>summary|data_coverage)"
    r"|environmental_findings\[(?P<finding>\d+)\]"
    r"|ranked_recommendations\[(?P<ranked>\d+)\](?:\.narrative)?"
    r"|excluded_options\[(?P<excluded>\d+)\](?:\.narrative)?"
    r"|evidence\[(?P<evidence>[^\]]+)\]"
    r"|limitations\[(?P<limitation>\d+)\]"
    r"|assumptions\[(?P<assumption>\d+)\])$"
)
"""Validator paths that name one replaceable statement (P23)."""


def _split_problem(problem: str) -> tuple[str, str]:
    """Split ``[code] location: detail`` into (code, location)."""
    if not problem.startswith("[") or "]" not in problem:
        return "unspecified", problem
    code, _, rest = problem[1:].partition("]")
    location, _, _detail = rest.strip().partition(": ")
    return code, location


def _statement_key(match: re.Match[str]) -> str:
    """Canonical location for a matched statement path (narratives fold in)."""
    groups = match.groupdict()
    if groups["single"] is not None:
        return groups["single"]
    if groups["finding"] is not None:
        return f"environmental_findings[{groups['finding']}]"
    if groups["ranked"] is not None:
        return f"ranked_recommendations[{groups['ranked']}]"
    if groups["excluded"] is not None:
        return f"excluded_options[{groups['excluded']}]"
    if groups["evidence"] is not None:
        return f"evidence[{groups['evidence']}]"
    if groups["limitation"] is not None:
        return f"limitations[{groups['limitation']}]"
    return f"assumptions[{groups['assumption']}]"


def group_by_statement(
    problems: list[str],
) -> tuple[dict[str, list[str]], list[str]]:
    """Group validator problems by statement location.

    Returns (location -> sorted unique codes, non-statement problems in
    input order). Ranked/excluded narrative paths fold into their
    recommendation; evidence entries group by chunk id.
    """
    grouped: dict[str, set[str]] = {}
    rest: list[str] = []
    for problem in problems:
        code, location = _split_problem(problem)
        match = _STATEMENT_PATH_RE.match(location)
        if match is None:
            rest.append(problem)
            continue
        grouped.setdefault(_statement_key(match), set()).add(code)
    return {key: sorted(codes) for key, codes in grouped.items()}, rest


def statement_locations(report: Report) -> list[str]:
    """Counted-statement locations in render order (validator vocabulary)."""
    locations = ["summary"]
    locations.extend(
        f"environmental_findings[{i}]" for i in range(len(report.environmental_findings))
    )
    locations.extend(
        f"ranked_recommendations[{i}]" for i in range(len(report.ranked_recommendations))
    )
    locations.extend(
        f"excluded_options[{i}]" for i in range(len(report.excluded_options))
    )
    locations.extend(f"limitations[{i}]" for i in range(len(report.limitations)))
    locations.extend(f"assumptions[{i}]" for i in range(len(report.assumptions)))
    locations.append("data_coverage")
    return locations


def count_model_statements(report: Report) -> tuple[int, int]:
    """(model-written, total) counted statements from the origins map.

    Legacy reports without stamps fall back to the report-level flag: a
    fallback counts as all-platform, an accepted draft as all-model.
    """
    origins = report.statement_origins
    if not origins:
        total = len(statement_locations(report))
        return (0, total) if report.fallback else (total, total)
    model = sum(1 for origin in origins.values() if origin == "model")
    return model, len(origins)


@dataclass
class CompositeResult:
    """A composite report plus what changed (caller must re-validate it)."""

    report: Report
    replaced: dict[str, list[str]] = field(default_factory=dict)
    """Composite location -> sorted codes that forced replacement."""
    dropped: dict[str, list[str]] = field(default_factory=dict)
    """Model location -> sorted codes (no safe counterpart existed)."""
    origins: dict[str, str] = field(default_factory=dict)
    """Composite counted-statement location -> "model" | "platform"."""


def _finding_counterpart(fallback: Report, output_ids: list[str]):
    """Fallback finding sharing a non-bundle tool output id, if any."""
    wanted = [o for o in output_ids if o != "bundle"]
    for finding in fallback.environmental_findings:
        if any(o in finding.tool_output_ids for o in wanted):
            return finding
    return None


def build_composite(
    model: Report, fallback: Report, problems: list[str]
) -> CompositeResult | None:
    """Compose kept model statements + fallback counterparts.

    Returns None when a problem has no statement location (the caller ships
    the full fallback) or when the composite cannot satisfy the schema.
    Origins and replaced/dropped maps use composite positions, except dropped
    entries, which keep their model positions (they are gone).
    """
    grouped, rest = group_by_statement(problems)
    if rest:
        return None
    origins: dict[str, str] = {}
    replaced: dict[str, list[str]] = {}
    dropped: dict[str, list[str]] = {}

    summary = model.summary
    if grouped.get("summary"):
        summary = fallback.summary
        origins["summary"] = "platform"
        replaced["summary"] = grouped["summary"]
    else:
        origins["summary"] = "model"

    findings = []
    for index, finding in enumerate(model.environmental_findings):
        codes = grouped.get(f"environmental_findings[{index}]", [])
        if not codes:
            findings.append(finding)
            origins[f"environmental_findings[{len(findings) - 1}]"] = "model"
            continue
        counterpart = _finding_counterpart(fallback, finding.tool_output_ids)
        if counterpart is None:
            dropped[f"environmental_findings[{index}]"] = codes
            continue
        findings.append(counterpart)
        location = f"environmental_findings[{len(findings) - 1}]"
        origins[location] = "platform"
        replaced[location] = codes

    fallback_ranked = {r.intervention_id: r for r in fallback.ranked_recommendations}
    ranked = []
    for index, rec in enumerate(model.ranked_recommendations):
        codes = grouped.get(f"ranked_recommendations[{index}]", [])
        if not codes:
            ranked.append(rec)
            origins[f"ranked_recommendations[{len(ranked) - 1}]"] = "model"
            continue
        counterpart = fallback_ranked.get(rec.intervention_id)
        if counterpart is None:
            dropped[f"ranked_recommendations[{index}]"] = codes
            continue
        ranked.append(counterpart)
        location = f"ranked_recommendations[{len(ranked) - 1}]"
        origins[location] = "platform"
        replaced[location] = codes

    fallback_excluded = {o.intervention_id: o for o in fallback.excluded_options}
    excluded = []
    for index, opt in enumerate(model.excluded_options):
        codes = grouped.get(f"excluded_options[{index}]", [])
        if not codes:
            excluded.append(opt)
            origins[f"excluded_options[{len(excluded) - 1}]"] = "model"
            continue
        counterpart = fallback_excluded.get(opt.intervention_id)
        if counterpart is None:
            dropped[f"excluded_options[{index}]"] = codes
            continue
        excluded.append(counterpart)
        location = f"excluded_options[{len(excluded) - 1}]"
        origins[location] = "platform"
        replaced[location] = codes

    fallback_evidence = {item.chunk_id: item for item in fallback.evidence}
    evidence = []
    for item in model.evidence:
        location = f"evidence[{item.chunk_id}]"
        codes = grouped.get(location, [])
        if not codes:
            evidence.append(item)
            continue
        counterpart = fallback_evidence.get(item.chunk_id)
        if counterpart is None:
            dropped[location] = codes
            continue
        evidence.append(counterpart)
        replaced[location] = codes

    limitations = []
    for index, text in enumerate(model.limitations):
        codes = grouped.get(f"limitations[{index}]", [])
        if not codes:
            limitations.append(text)
            origins[f"limitations[{len(limitations) - 1}]"] = "model"
            continue
        if index >= len(fallback.limitations):
            dropped[f"limitations[{index}]"] = codes
            continue
        limitations.append(fallback.limitations[index])
        location = f"limitations[{len(limitations) - 1}]"
        origins[location] = "platform"
        replaced[location] = codes

    assumptions = []
    for index, text in enumerate(model.assumptions):
        codes = grouped.get(f"assumptions[{index}]", [])
        if not codes:
            assumptions.append(text)
            origins[f"assumptions[{len(assumptions) - 1}]"] = "model"
            continue
        if index >= len(fallback.assumptions):
            dropped[f"assumptions[{index}]"] = codes
            continue
        assumptions.append(fallback.assumptions[index])
        location = f"assumptions[{len(assumptions) - 1}]"
        origins[location] = "platform"
        replaced[location] = codes

    coverage = model.data_coverage
    if grouped.get("data_coverage"):
        coverage = fallback.data_coverage
        origins["data_coverage"] = "platform"
        replaced["data_coverage"] = grouped["data_coverage"]
    else:
        origins["data_coverage"] = "model"

    # Complete the citation set: replaced (fallback) statements may cite chunks
    # the model never listed. Add the fallback's own entries for those; chunks
    # outside the retrieved set still fail re-validation, by design.
    listed = {item.chunk_id for item in evidence}
    cited: set[str] = set()
    for statement in [summary, *findings, coverage]:
        cited.update(statement.evidence_ids)
    for rec in ranked:
        cited.update(rec.narrative.evidence_ids)
    for opt in excluded:
        cited.update(opt.narrative.evidence_ids)
    for chunk_id in sorted(cited - listed):
        counterpart = fallback_evidence.get(chunk_id)
        if counterpart is not None:
            evidence.append(counterpart)

    try:
        report = Report(
            schema_version=model.schema_version,
            generator=model.generator,
            fallback=False,
            fallback_note=None,
            summary=summary,
            environmental_findings=findings,
            evidence=evidence,
            ranked_recommendations=ranked,
            excluded_options=excluded,
            limitations=limitations,
            assumptions=assumptions,
            data_coverage=coverage,
            provenance_refs=list(model.provenance_refs),
            acceptance="ai-partial" if (replaced or dropped) else "ai-accepted",
            statement_origins=origins,
            replaced_statements=replaced,
            dropped_statements=dropped,
        )
    except ValidationError:
        return None
    return CompositeResult(
        report=report, replaced=replaced, dropped=dropped, origins=origins
    )


def stamp_accepted(report: Report) -> Report:
    """Stamp a fully valid model draft as ai-accepted (all-model origins)."""
    return report.model_copy(
        update={
            "acceptance": "ai-accepted",
            "statement_origins": {
                location: "model" for location in statement_locations(report)
            },
            "replaced_statements": {},
            "dropped_statements": {},
        }
    )
