"""Prompt templates for the report draft. Templates live in ``prompts/*.txt``.

Retrieved text is untrusted data: every passage is wrapped in an explicit
``RETRIEVED`` block whose header states the citable ids, delimiter-looking
sequences inside the passage are neutralised, and over-long passages are
truncated with a visible marker. The system prompt's instruction hierarchy
declares these blocks non-instructional; the validator independently rejects
any draft that obeyed injected instructions (unknown ids, banned vocabulary,
unverifiable citations).
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources

from climateadapt.llm.provider import LLMMessage, LLMRequest
from climateadapt.rag.models import Chunk

EVIDENCE_OPEN = "<<<RETRIEVED-DATA"
EVIDENCE_CLOSE = "<<<END-RETRIEVED-DATA>>>"
MAX_PASSAGE_CHARS = 1500
TRUNCATION_MARKER = " [...] (truncated)"


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
    citations: Sequence[str] | None = None,
    *,
    max_chars: int = MAX_PASSAGE_CHARS,
) -> str:
    """Render retrieved chunks as delimited, clearly-labelled data blocks."""
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
            lines.append(f"citation: {citations[index]}")
        lines.append(passage)
        lines.append(EVIDENCE_CLOSE)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_report_request(
    *,
    bundle_json: str,
    ranking_json: str,
    evidence_block: str,
    generator_label: str,
    max_tokens: int = 4000,
) -> LLMRequest:
    """Assemble the system + user messages for one report draft."""
    user_text = load_user_template().format(
        generator_label=generator_label,
        bundle_json=bundle_json,
        ranking_json=ranking_json,
        evidence_block=evidence_block,
    )
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=load_system_prompt()),
            LLMMessage(role="user", content=user_text),
        ],
        max_tokens=max_tokens,
    )
