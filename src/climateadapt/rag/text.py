"""Deterministic text normalisation shared by chunking and citation verification."""

from __future__ import annotations

import re
import unicodedata

_SOFT_HYPHEN = "\u00ad"
_DOT_LEADERS = re.compile(r"[.\u2026_]{3,}")
_LINE_BREAK_HYPHEN = re.compile(r"([^\W\d_])-[ \t]*\r?\n[ \t]*([a-z])")


def normalize_text(text: str) -> str:
    """NFKC, drop soft hyphens, rejoin words hyphenated at line ends, drop dot leaders.

    Trade-off: a genuine compound split at a line end ("water-\\nuse") is joined too.
    """
    text = unicodedata.normalize("NFKC", text).replace(_SOFT_HYPHEN, "")
    text = _LINE_BREAK_HYPHEN.sub(r"\1\2", text)
    text = _DOT_LEADERS.sub(" ", text)
    return " ".join(text.split())


def words(text: str) -> list[str]:
    return normalize_text(text).split()