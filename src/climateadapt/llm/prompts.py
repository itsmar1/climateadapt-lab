"""Prompt templates for the report draft. Templates live in ``prompts/*.txt``.

Retrieved text is untrusted data: every passage is wrapped in an explicit
``RETRIEVED`` block whose header states the citable ids, delimiter-looking
sequences inside the passage are neutralised, and over-long passages are
truncated with a visible marker. The system prompt's instruction hierarchy
declares these blocks non-instructional; the validator independently rejects
any draft that obeyed injected instructions (unknown ids, banned vocabulary,
unverifiable citations).

P18: ``format_registry_block`` states the validator's exact ``(output_id,
field)`` vocabulary so the model never has to guess it (the P10 draft
invented ``environmental_bundle`` and ``entries[N].result.<field>`` paths).
``build_repair_request`` feeds a rejected draft's validator problems back for
at most one repair attempt; the repair output is validated exactly as before.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources
from typing import TYPE_CHECKING

from climateadapt.llm.provider import LLMMessage, LLMRequest
from climateadapt.rag.models import Chunk

if TYPE_CHECKING:
    from climateadapt.llm.report import ToolOutputRegistry
    from climateadapt.rag.citations import Citation

EVIDENCE_OPEN = "<<<RETRIEVED-DATA"
EVIDENCE_CLOSE = "<<<END-RETRIEVED-DATA>>>"
MAX_PASSAGE_CHARS = 1500
TRUNCATION_MARKER = " [...] (truncated)"
MAX_REPAIR_PROBLEMS = 20
MAX_REPAIR_DRAFT_CHARS = 8000
MAX_REPAIR_PROBLEM_CHARS = 500
"""Per-problem budget: keeps the offending sentence + matched phrase (P22)."""


def _template(name: str) -> str:
    return (resources.files("climateadapt.llm") / "prompts" / name).read_text(
        encoding="utf-8"
    )


def load_system_prompt() -> str:
    return _template("report_system.txt")


def load_user_template() -> str:
    return _template("report_user.txt")


def escape_passage(text: str) -> str:
    """Neutralise delimiter-looking sequences inside untrusted retrieved text."""
    return text.replace("<<<", "\u00ab").replace(">>>", "\u00bb")


def format_evidence_block(
    chunks: Sequence[Chunk],
    citations: Sequence[str] | Sequence[Citation] | None = None,
    *,
    max_chars: int = MAX_PASSAGE_CHARS,
) -> str:
    """Render retrieved chunks as delimited, clearly-labelled data blocks.

    ``citations`` accepts legacy formatted strings (one ``citation:`` line) or
    full :class:`Citation` objects (P18: every evidence field the validator
    checks — ``citation``/``pages``/``landing_url``/``license``/
    ``license_status`` — rendered for verbatim copying).
    """
    if citations is not None and len(citations) != len(chunks):
        raise ValueError("citations must match chunks one-to-one.")
    if not chunks:
        return "(no passages retrieved: cite no evidence_ids)"
    blocks: list[str] = []
    for index, chunk in enumerate(chunks):
        passage = escape_passage(chunk.text)
        if len(passage) > max_chars:
            passage = passage[:max_chars] + TRUNCATION_MARKER
        header = (
            f'{EVIDENCE_OPEN} chunk_id="{chunk.chunk_id}" doc_id="{chunk.doc_id}" '
            f'pages="{chunk.page_start}-{chunk.page_end}">>>'
        )
        lines = [header]
        if citations is not None:
            citation = citations[index]
            if isinstance(citation, str):
                lines.append(f"citation: {citation}")
            else:
                lines.append(f"citation: {citation.formatted}")
                lines.append(f"pages: {citation.pages}")
                lines.append(f"landing_url: {citation.landing_url}")
                lines.append(f"license: {citation.license}")
                lines.append(f"license_status: {citation.license_status}")
        lines.append(passage)
        lines.append(EVIDENCE_CLOSE)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_registry_block(
    registry: ToolOutputRegistry,
    chunk_ids: Sequence[str],
) -> str:
    """Render the validator's exact citable vocabulary for the prompt.

    Lists every allowed tool-output id, every ``output_id.field = value``
    number, the ranking/constraints texts and reason codes, the allowed
    evidence ids, and the repeatable dates — plus one worked ``numbers[]``
    example built from this run's real values. The model must use ONLY these
    ids; the historic invented schemes are named as banned.
    """
    lines = ["ALLOWED IDS AND VALUES (authoritative; copy exactly, use ONLY these)"]
    output_ids = sorted(registry.outputs)
    lines.append("Tool output ids (only these in tool_output_ids, "
                 "numbers[].tool_output_id, provenance_refs):")
    for output_id in output_ids:
        lines.append(f"- {output_id}")
    lines.append("Numbers (output_id.field = exact value; copy value exactly, "
                 "declare each numeral in numbers[]):")
    any_numbers = False
    for output_id in output_ids:
        for field in sorted(registry.outputs[output_id].values):
            value = registry.outputs[output_id].values[field]
            lines.append(f"- {output_id}.{field} = {value!r}")
            any_numbers = True
    if not any_numbers:
        lines.append("- (no numeric tool outputs this run: write no numerals)")
    lines.append("Texts (copy exactly where the schema requires an echo):")
    any_texts = False
    for output_id in output_ids:
        for field in sorted(registry.outputs[output_id].texts):
            text = registry.outputs[output_id].texts[field]
            lines.append(f'- {output_id}.{field} = "{text}"')
            any_texts = True
    if not any_texts:
        lines.append("- (no echo texts this run)")
    lines.append("Evidence ids (only these in evidence_ids; "
                 "list each cited id in evidence[]):")
    if chunk_ids:
        for chunk_id in sorted(chunk_ids):
            lines.append(f"- {chunk_id}")
    else:
        lines.append("- (no passages retrieved: cite no evidence_ids)")
    lines.append("Dates (you may repeat these YYYY-MM strings verbatim; "
                 "no other dates):")
    if registry.dates:
        for date in sorted(registry.dates):
            lines.append(f"- {date}")
    else:
        lines.append("- (none)")
    lines.append(
        "BANNED (never write these; the validator rejects them): "
        '"environmental_bundle", "recommendations", JSON paths like '
        '"entries[0].result.spi", and any id not listed above.'
    )
    lines.append(
        "NUMERALS (strict): write a numeral only if it appears above with exactly "
        "that value (copy verbatim and declare it). Any other number — layer "
        "ranges, resolutions, distances, counts — must be words, never digits."
    )
    lines.append(_worked_example(registry))
    return "\n".join(lines)


def _worked_example(registry: ToolOutputRegistry) -> str:
    """One short valid statement built from this run's real values."""
    pick_id: str | None = None
    pick_fields: list[str] = []
    for output_id in sorted(registry.outputs):
        fields = sorted(registry.outputs[output_id].values)
        if fields:
            pick_id, pick_fields = output_id, fields[:2]
            break
    if pick_id is None:
        return (
            "WORKED EXAMPLE (format only):\n"
            '{"text": "No numeric outputs were computed.", '
            '"evidence_ids": [], "tool_output_ids": ["bundle"], "numbers": []}\n'
            "Every numeral in text must appear in numbers[] with its exact "
            "tool value; here there are no numerals."
        )
    values = registry.outputs[pick_id].values
    pairs = ", ".join(f"{f} {values[f]!r}" for f in pick_fields)
    numbers = ", ".join(
        f'{{"value": {values[f]!r}, "unit": null, '
        f'"tool_output_id": "{pick_id}", "field": "{f}"}}'
        for f in pick_fields
    )
    return (
        "WORKED EXAMPLE (shape to copy; values are from THIS run):\n"
        f'{{"text": "{pick_id}: {pairs}.", "evidence_ids": [], '
        f'"tool_output_ids": ["{pick_id}"], "numbers": [{numbers}]}}\n'
        "Every numeral in text appears in numbers[] with the exact tool value."
    )


def build_repair_request(
    original: LLMRequest,
    draft_text: str | None,
    problems: Sequence[str],
    *,
    max_problems: int = MAX_REPAIR_PROBLEMS,
    max_draft_chars: int = MAX_REPAIR_DRAFT_CHARS,
) -> LLMRequest:
    """Build the single repair attempt: original prompt + rejection feedback.

    Problem lines keep their offending sentence and matched phrase (P22) so the
    model can locate each failure; the draft excerpt shows the full context.
    """
    shown = list(problems[:max_problems])
    omitted = len(problems) - len(shown)
    problem_lines = "\n".join(
        f"- {problem[:MAX_REPAIR_PROBLEM_CHARS]}" for problem in shown
    )
    if omitted > 0:
        problem_lines += f"\n- (... and {omitted} more problems, same rules)"
    excerpt = (draft_text or "(no draft text returned)")[:max_draft_chars]
    if draft_text is not None and len(draft_text) > max_draft_chars:
        excerpt += " [...] (draft truncated)"
    repair_context = (
        "\n\nPREVIOUS DRAFT REJECTED — FIX EVERY PROBLEM BELOW\n"
        "Your previous output failed validation. Output ONE corrected JSON "
        "object matching the same schema and rules (verbatim ids, declared "
        "numbers, exact citations). For each number problem, replace the number "
        "with words or delete the sentence; do not add new numbers. "
        "Problems to fix:\n"
        f"{problem_lines}\n"
        "Previous invalid draft (excerpt, fix it; do not repeat its mistakes):\n"
        f"{excerpt}"
    )
    system = original.messages[0]
    user = original.messages[-1]
    return LLMRequest(
        messages=[
            LLMMessage(role=system.role, content=system.content),
            LLMMessage(role="user", content=user.content + repair_context),
        ],
        max_tokens=original.max_tokens,
        temperature=original.temperature,
        response_format=original.response_format,
    )


def build_report_request(
    *,
    bundle_json: str,
    ranking_json: str,
    evidence_block: str,
    generator_label: str,
    max_tokens: int = 4000,
    registry_block: str | None = None,
) -> LLMRequest:
    """Assemble the system + user messages for one report draft.

    ``registry_block`` (P18, from :func:`format_registry_block`) states the
    exact allowed ids/values; it is inserted before the retrieved passages so
    the model reads the vocabulary before the prose it must cite. Omitted
    callers keep the legacy prompt shape.
    """
    user_text = load_user_template().format(
        generator_label=generator_label,
        bundle_json=bundle_json,
        ranking_json=ranking_json,
        evidence_block=evidence_block,
    )
    if registry_block:
        marker = "RETRIEVED PASSAGES"
        if marker in user_text:
            user_text = user_text.replace(
                marker, f"{registry_block}\n\n{marker}", 1
            )
        else:
            user_text = f"{user_text}\n\n{registry_block}"
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=load_system_prompt()),
            LLMMessage(role="user", content=user_text),
        ],
        max_tokens=max_tokens,
    )
