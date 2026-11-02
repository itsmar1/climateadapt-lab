"""Client-side report validation. Nothing model-written reaches a user unvalidated.

``validate_report`` enforces the traceability contract structurally: schema
conformance, known evidence ids, citations rebuilt and compared verbatim plus
``rag.citations.verify_citation``, every prose numeral traced through a declared
number to a registry value (digits inside known dataset/product identifiers
such as ``ERA5-Land`` are names, not claims), mandatory limitations and
provenance, and bans on
severity labels, efficacy/cost claims, and currency/percent tokens. Any failure
means the draft is rejected and the caller must serve the deterministic
fallback instead (see :mod:`climateadapt.llm.fallback`).

Problem strings carry stable ``[code]`` prefixes so the fallback note can quote
codes; ``undeclared-number`` and ``efficacy-claim`` additionally quote the
offending sentence (and the matched phrase) so the repair turn can fix them.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from climateadapt.llm.report import (
    EvidenceItem,
    ExcludedOption,
    RankedRecommendation,
    Report,
    Statement,
    ToolOutputRegistry,
    constraints_output_id,
    ranking_output_id,
)
from climateadapt.rag.citations import build_citation, verify_citation
from climateadapt.rag.manifest import Manifest
from climateadapt.rag.models import Chunk, Page

NUMBER_RE = re.compile(r"(?<!\d)[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")
"""Numeric literals in prose. A leading sign after a digit is a range dash."""

PAGE_REF_RE = re.compile(
    r"PDF\s+p{1,2}\.\s*\d+(?:\s*-\s*\d+)?"
    r"|\(printed\s+p\.\s*[^)]*\)"
    r"|\(PDF index; no printed label\)"
    r"|\bp{1,2}\.\s*\d+(?:\s*-\s*\d+)?"
)
"""Citation page references (PDF index / printed label) carry no tool numbers."""

SEVERITY_RES = (
    re.compile(r"\bseverity\b", re.IGNORECASE),
    re.compile(
        r"\b(severe|severely|extreme|extremely|exceptional|exceptionally"
        r"|moderate|moderately|mild|abnormally)\s+drought\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(abnormally|moderately|severely|extremely|exceptionally)\s+dry\w*\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bspi\s+categor\w*\b", re.IGNORECASE),
    re.compile(r"\busdm\b", re.IGNORECASE),
    re.compile(r"\bD[0-4]\b"),
)
"""Banned drought-severity vocabulary (AGENTS.md §7.6; no exemptions, see prompts)."""

FORBIDDEN_TOKEN_RES = (
    re.compile(r"%"),
    re.compile(r"\bpercent(age)?s?\b", re.IGNORECASE),
    re.compile(r"[$€£]"),
    re.compile(r"\b(USD|EUR|MAD|DH|dirhams?|dollars?|euros?)\b", re.IGNORECASE),
    re.compile(r"/ha\b", re.IGNORECASE),
    re.compile(r"\bper hectare\b", re.IGNORECASE),
)
"""Currency/percent/yield-unit tokens: never writable, even in limitations."""

EFFICACY_RE = re.compile(
    r"\b(increas\w*|decreas\w*|reduc\w*|improv\w*|gains?|savings?|saves?"
    r"|efficien\w*|effectiv\w*|yields?|profits?|incomes?|payback|cheaper|expensive)\b",
    re.IGNORECASE,
)
"""Efficacy/cost-quantity stems, banned in ranked narratives (benefits are unknown)."""

DATASET_IDENTIFIER_RE = re.compile(
    r"\bERA5(?:-Land)?\b|\bCHIRPS\s+v?3(?:\.0)?\b",
    re.IGNORECASE,
)
"""Dataset/product names whose digits are identifiers, not measurements (P22).

``ERA5``/``ERA5-Land`` (also lowercase inside
``reanalysis-era5-land-monthly-means``) and ``CHIRPS v3``/``CHIRPS v3.0`` name
this project's data products (see ``data/era5_land.py`` DATASET_NAME/DATASET_ID
and the CHIRPS DATA_SOURCE strings). Version digits count only attached to the
product name: a bare "3" or "5", a resolution, or a year quoted outside the
full data_source echo stays a numeric claim and must be declared.
"""

MAX_EVIDENCE_CHARS = 200
"""Cap for offending sentences quoted in problem strings (repair evidence)."""

_SENTENCE_RE = re.compile(
    r".*?(?:[;!?]|(?<!\be\.g)(?<!\bi\.e)(?<!\betc)\.(?=\s+[A-Z0-9])"
    r"|\.(?=\s*$)|\s*$)",
    re.DOTALL,
)
"""Sentence spans; a period ends one only before a capital/digit or the end.

A period between digits ("7.8") or inside an abbreviation ("e.g. ...") is not
a sentence end, so offending-sentence evidence is never cut mid-number (P23).
Only the quoted context changes — which numerals are flagged is untouched."""


def _sentence_around(text: str, start: int) -> str:
    """The sentence of ``text`` containing offset ``start``, capped."""
    for match in _SENTENCE_RE.finditer(text):
        if match.start() <= start < match.end():
            sentence = " ".join(match.group(0).split())
            if len(sentence) > MAX_EVIDENCE_CHARS:
                sentence = sentence[:MAX_EVIDENCE_CHARS] + " [...]"
            return sentence
    return ""

REL_TOL = 1e-9
ABS_TOL = 1e-9
"""Number equality: JSON round-trips floats exactly, so copies must match."""


@dataclass
class ValidationContext:
    """Everything a draft is checked against (all deterministic)."""

    registry: ToolOutputRegistry
    chunks: dict[str, Chunk] = field(default_factory=dict)
    manifest: Manifest | None = None
    pages_by_doc: Mapping[str, Sequence[Page]] = field(default_factory=dict)


@dataclass
class ValidationResult:
    valid: bool
    problems: list[str]
    report: Report | None


def _problem(code: str, detail: str) -> str:
    return f"[{code}] {detail}"


def _close(value: float, candidates: Sequence[float]) -> bool:
    return any(math.isclose(value, c, rel_tol=REL_TOL, abs_tol=ABS_TOL) for c in candidates)


def _strip_known(text: str, ctx: ValidationContext) -> str:
    """Remove tokens whose digits are identifiers, not measurements.

    Replacements keep the original length (spaces), so numeral positions in the
    scrubbed text map back to the offending sentence in the original text.
    """
    scrubbed = DATASET_IDENTIFIER_RE.sub(
        lambda match: " " * len(match.group(0)), text
    )
    for token in list(ctx.chunks) + list(ctx.registry.outputs):
        if token:
            scrubbed = scrubbed.replace(token, " " * len(token))
    for output in ctx.registry.outputs.values():
        for known in output.texts.values():
            if known:
                scrubbed = scrubbed.replace(known, " " * len(known))
    for date in ctx.registry.dates:
        if date:
            scrubbed = scrubbed.replace(date, " " * len(date))
    return PAGE_REF_RE.sub(lambda match: " " * len(match.group(0)), scrubbed)


def _literals(text: str) -> list[tuple[str, float, int, int]]:
    """Numeral literals with values and spans (spans map to the source text)."""
    found: list[tuple[str, float, int, int]] = []
    for match in NUMBER_RE.finditer(text):
        raw = match.group(0)
        literal = raw.lstrip("+")
        try:
            value = float(literal.replace(",", ""))
        except ValueError:
            continue
        start = match.start() + (len(raw) - len(literal))
        found.append((literal, value, start, match.end()))
    return found


def _check_numbers_in_text(
    text: str,
    declared: Sequence[float],
    ctx: ValidationContext,
    path: str,
    problems: list[str],
) -> None:
    scrubbed = _strip_known(text, ctx)
    for literal, value, start, _end in _literals(scrubbed):
        if not _close(value, declared):
            sentence = _sentence_around(text, start)
            problems.append(
                _problem(
                    "undeclared-number",
                    f"{path}: numeral {literal!r} is not a declared tool-output "
                    f"value. Offending sentence: {sentence!r}.",
                )
            )


def _check_banned_vocabulary(text: str, path: str, problems: list[str]) -> None:
    for pattern in SEVERITY_RES:
        if pattern.search(text):
            problems.append(
                _problem("drought-label", f"{path}: banned severity vocabulary.")
            )
            break
    for pattern in FORBIDDEN_TOKEN_RES:
        if pattern.search(text):
            problems.append(
                _problem("forbidden-token", f"{path}: banned currency/percent token.")
            )
            break


def _statements(report: Report) -> list[tuple[str, Statement]]:
    items: list[tuple[str, Statement]] = [
        ("summary", report.summary),
        ("data_coverage", report.data_coverage),
    ]
    items.extend(
        (f"environmental_findings[{i}]", s)
        for i, s in enumerate(report.environmental_findings)
    )
    for i, rec in enumerate(report.ranked_recommendations):
        items.append((f"ranked_recommendations[{i}].narrative", rec.narrative))
    for i, opt in enumerate(report.excluded_options):
        items.append((f"excluded_options[{i}].narrative", opt.narrative))
    return items


def _check_statement(
    path: str, statement: Statement, ctx: ValidationContext, problems: list[str]
) -> None:
    for evidence_id in statement.evidence_ids:
        if evidence_id not in ctx.chunks:
            problems.append(
                _problem("unknown-evidence", f"{path}: {evidence_id!r} was not retrieved.")
            )
    for output_id in statement.tool_output_ids:
        if not ctx.registry.has(output_id):
            problems.append(
                _problem("unknown-tool-output", f"{path}: {output_id!r} is not a tool output.")
            )
    declared: list[float] = []
    for number in statement.numbers:
        expected = ctx.registry.lookup_number(number.tool_output_id, number.field)
        if expected is None:
            problems.append(
                _problem(
                    "unknown-tool-output",
                    f"{path}: {number.tool_output_id}:{number.field} is not registered.",
                )
            )
            continue
        declared.append(number.value)
        if not math.isclose(
            number.value, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL
        ):
            problems.append(
                _problem(
                    "number-mismatch",
                    f"{path}: {number.tool_output_id}:{number.field} is "
                    f"{number.value!r}, tool output is {expected!r}.",
                )
            )
    _check_numbers_in_text(statement.text, declared, ctx, path, problems)
    _check_banned_vocabulary(statement.text, path, problems)


def _check_evidence(
    item: EvidenceItem, ctx: ValidationContext, problems: list[str]
) -> None:
    path = f"evidence[{item.chunk_id}]"
    chunk = ctx.chunks.get(item.chunk_id)
    if chunk is None:
        problems.append(_problem("unknown-evidence", f"{path}: chunk was not retrieved."))
        return
    if ctx.manifest is None:
        problems.append(_problem("citation-unverifiable", f"{path}: no manifest."))
        return
    if item.doc_id != chunk.doc_id:
        problems.append(
            _problem("citation-mismatch", f"{path}: doc_id {item.doc_id!r} is wrong.")
        )
        return
    try:
        expected = build_citation(chunk, ctx.manifest.get(chunk.doc_id))
    except (KeyError, ValueError) as exc:
        problems.append(_problem("citation-mismatch", f"{path}: {exc}"))
        return
    for field_name in ("citation", "pages", "landing_url", "license", "license_status"):
        actual = getattr(item, field_name)
        want = getattr(expected, field_name if field_name != "citation" else "formatted")
        if actual != want:
            problems.append(
                _problem("citation-mismatch", f"{path}: {field_name} does not match.")
            )
    if verify_citation(chunk, ctx.manifest, ctx.pages_by_doc):
        problems.append(
            _problem("citation-unverifiable", f"{path}: chunk fails provenance check.")
        )


def _check_ranked(
    index: int, rec: RankedRecommendation, ctx: ValidationContext, problems: list[str]
) -> None:
    path = f"ranked_recommendations[{index}]"
    output = ctx.registry.outputs.get(ranking_output_id(rec.intervention_id))
    if output is None:
        problems.append(
            _problem("unknown-intervention", f"{path}: {rec.intervention_id!r} was not ranked.")
        )
        return
    if ranking_output_id(rec.intervention_id) not in rec.narrative.tool_output_ids:
        problems.append(_problem("missing-ranking-ref", f"{path}: narrative must cite it."))
    if output.label is not None and rec.name != output.label:
        problems.append(_problem("name-mismatch", f"{path}: name does not match."))
    for field_name in ("benefit", "cost", "risk"):
        if getattr(rec, field_name) != output.texts.get(field_name):
            problems.append(
                _problem("echo-mismatch", f"{path}: {field_name} differs from the catalog.")
            )
    match = EFFICACY_RE.search(rec.narrative.text)
    if match is not None:
        sentence = _sentence_around(rec.narrative.text, match.start())
        problems.append(
            _problem(
                "efficacy-claim",
                f"{path}: narrative states efficacy/cost effects. "
                f"Matched phrase: {match.group(0)!r}. "
                f"Offending sentence: {sentence!r}.",
            )
        )


def _check_excluded(
    index: int,
    opt: ExcludedOption,
    ctx: ValidationContext,
    problems: list[str],
) -> None:
    path = f"excluded_options[{index}]"
    output = ctx.registry.outputs.get(constraints_output_id(opt.intervention_id))
    if output is None:
        problems.append(
            _problem(
                "unknown-intervention", f"{path}: {opt.intervention_id!r} was not excluded."
            )
        )
        return
    if constraints_output_id(opt.intervention_id) not in opt.narrative.tool_output_ids:
        problems.append(_problem("missing-constraints-ref", f"{path}: narrative must cite it."))
    if output.label is not None and opt.name != output.label:
        problems.append(_problem("name-mismatch", f"{path}: name does not match."))
    expected_codes = (
        output.texts.get("reason_codes", "").split(",")
        if output.texts.get("reason_codes")
        else []
    )
    if set(opt.reason_codes) != set(expected_codes) or len(set(opt.reason_codes)) != len(
        opt.reason_codes
    ):
        problems.append(
            _problem("reason-mismatch", f"{path}: reason codes differ from constraints.")
        )


def validate_report(
    data: dict[str, Any] | Report,
    ctx: ValidationContext,
    *,
    allow_fallback: bool = False,
) -> ValidationResult:
    """Validate a model draft (``allow_fallback=False``) or a fallback report."""
    if isinstance(data, Report):
        report = data
    else:
        try:
            report = Report.model_validate(data)
        except ValidationError as exc:
            problems = [
                _problem("schema", f"{'.'.join(map(str, e['loc']))}: {e['msg']}")
                for e in exc.errors()[:8]
            ]
            return ValidationResult(valid=False, problems=problems, report=None)

    problems: list[str] = []
    if report.fallback and not allow_fallback:
        problems.append(_problem("fallback-flag", "Model output must not set fallback."))
    if report.fallback and not report.fallback_note:
        problems.append(_problem("fallback-note", "Fallback reports need a fallback note."))
    if not report.fallback and report.fallback_note:
        problems.append(_problem("fallback-note", "Only fallback reports carry a note."))

    for path, statement in _statements(report):
        _check_statement(path, statement, ctx, problems)

    seen_evidence: set[str] = set()
    for item in report.evidence:
        if item.chunk_id in seen_evidence:
            problems.append(
                _problem("citation-mismatch", f"evidence[{item.chunk_id}]: duplicated.")
            )
        seen_evidence.add(item.chunk_id)
        _check_evidence(item, ctx, problems)
    used_ids = {
        evidence_id
        for _, statement in _statements(report)
        for evidence_id in statement.evidence_ids
    }
    for evidence_id in sorted(used_ids - seen_evidence):
        problems.append(
            _problem("missing-evidence-entry", f"{evidence_id!r} is cited but not listed.")
        )

    for index, rec in enumerate(report.ranked_recommendations):
        _check_ranked(index, rec, ctx, problems)
    for index, opt in enumerate(report.excluded_options):
        _check_excluded(index, opt, ctx, problems)

    registry_numbers = ctx.registry.all_numbers()
    for index, text in enumerate(report.limitations):
        path = f"limitations[{index}]"
        if not text.strip():
            problems.append(_problem("empty-section", f"{path}: blank."))
            continue
        _check_numbers_in_text(text, registry_numbers, ctx, path, problems)
        _check_banned_vocabulary(text, path, problems)
    for index, text in enumerate(report.assumptions):
        path = f"assumptions[{index}]"
        _check_numbers_in_text(text, registry_numbers, ctx, path, problems)
        _check_banned_vocabulary(text, path, problems)
    if report.fallback_note:
        _check_numbers_in_text(
            report.fallback_note, registry_numbers, ctx, "fallback_note", problems
        )
        _check_banned_vocabulary(report.fallback_note, "fallback_note", problems)

    seen_refs: set[str] = set()
    for ref in report.provenance_refs:
        if ref in seen_refs:
            problems.append(_problem("missing-provenance", f"{ref!r}: duplicated."))
        seen_refs.add(ref)
        if not ctx.registry.has(ref):
            problems.append(_problem("missing-provenance", f"{ref!r} is not a tool output."))

    return ValidationResult(valid=not problems, problems=problems, report=report)
