"""Page-aware sliding-window chunking with verifiable provenance.

Chunks are windows of ``chunk_words`` words over the whole document, so a chunk may span a page
boundary; it records the page of its first and last word. Low-letter-ratio windows (mostly
numbers, for example tables) and tiny documents are DROPPED AND COUNTED, never silently lost.
``chunk_index`` counts windows including dropped ones, so gaps are visible.
Each chunk also carries the printed page labels of its first/last word (when the
PDF provides /PageLabels), a heuristic ``section_type`` ("body"/"references"),
and ``max_page_span`` optionally cuts windows that would span too many pages.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from climateadapt.rag.models import Chunk, Page, make_chunk_id
from climateadapt.rag.text import normalize_text, words


@dataclass(frozen=True)
class ChunkingParams:
    chunk_words: int = 220
    overlap_words: int = 40
    min_words: int = 30
    min_alpha_ratio: float = 0.45
    max_page_span: int | None = None

    def __post_init__(self) -> None:
        if self.chunk_words < 20:
            raise ValueError("chunk_words must be at least 20.")
        if not 0 <= self.overlap_words < self.chunk_words:
            raise ValueError("overlap_words must be >= 0 and smaller than chunk_words.")
        if not 1 <= self.min_words <= self.chunk_words:
            raise ValueError("min_words must be between 1 and chunk_words.")
        if not 0.0 <= self.min_alpha_ratio <= 1.0:
            raise ValueError("min_alpha_ratio must be between 0 and 1.")
        if self.max_page_span is not None and self.max_page_span < 1:
            raise ValueError("max_page_span must be at least 1.")


DEFAULT_CHUNKING_PARAMS = ChunkingParams()


@dataclass(frozen=True)
class ChunkingStats:
    n_pages: int
    n_empty_pages: int
    n_words: int
    n_chunks_kept: int
    n_chunks_dropped_short: int
    n_chunks_dropped_low_alpha: int
    n_chunks_cut_for_span: int = 0


def _alpha_ratio(text: str) -> float:
    non_space = sum(1 for ch in text if not ch.isspace())
    if non_space == 0:
        return 0.0
    return sum(1 for ch in text if ch.isalpha()) / non_space


_REFERENCE_HEADING = re.compile(
    r"^(references|bibliography|r\xe9f\xe9rences|bibliographie)\b", re.IGNORECASE
)
_CITATION_YEAR = re.compile(r"(?<!\w)(?:19|20)\d{2}(?!\w)")


def section_type_of(text: str) -> Literal["body", "references"]:
    """Heuristic tag: bibliography/reference-list chunks vs body text.

    A chunk is tagged "references" when it carries at least four citation years
    (19xx/20xx) at a density of >= 2 per 100 words, or when it opens with a
    references/bibliography heading (English or French) plus at least two years.
    Body text that merely cites a few works stays "body". The rule is
    deliberately conservative and is covered by tests, not tuned on the corpus.
    """
    years = len(_CITATION_YEAR.findall(text))
    density = years / max(1, len(text.split()))
    if years >= 4 and density >= 0.02:
        return "references"
    if years >= 2 and _REFERENCE_HEADING.match(text.strip()):
        return "references"
    return "body"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_document(
    doc_id: str, 
    pages: Sequence[Page], 
    params: ChunkingParams = DEFAULT_CHUNKING_PARAMS
) -> tuple[list[Chunk], ChunkingStats]:
    all_words: list[str] = []
    word_pages: list[int] = []
    word_labels: list[str | None] = []
    n_empty = 0
    for page in pages:
        page_words = words(page.text)
        if not page_words:
            n_empty += 1
        all_words.extend(page_words)
        word_pages.extend([page.page] * len(page_words))
        word_labels.extend([page.label] * len(page_words))

    total = len(all_words)
    step = params.chunk_words - params.overlap_words
    chunks: list[Chunk] = []
    dropped_short = dropped_alpha = cut_for_span = 0
    start = index = 0
    while start < total:
        end = min(start + params.chunk_words, total)
        if params.max_page_span is not None:
            full = end
            limit = word_pages[start] + params.max_page_span - 1
            while end - 1 > start and word_pages[end - 1] > limit:
                end -= 1
            if end < full:
                cut_for_span += 1
        text = " ".join(all_words[start:end])
        count = end - start
        if count < params.min_words:
            dropped_short += 1
        elif _alpha_ratio(text) < params.min_alpha_ratio:
            dropped_alpha += 1
        else:
            chunks.append(
                Chunk(
                    chunk_id=make_chunk_id(doc_id, index),
                    doc_id=doc_id,
                    chunk_index=index,
                    page_start=word_pages[start],
                    page_end=word_pages[end - 1],
                    label_start=word_labels[start],
                    label_end=word_labels[end - 1],
                    section_type=section_type_of(text),
                    word_count=count,
                    text=text,
                    text_sha256=sha256_text(text),
                )
            )
        index += 1
        if end == total:
            break
        start += step

    stats = ChunkingStats(
        n_pages=len(pages),
        n_empty_pages=n_empty,
        n_words=total,
        n_chunks_kept=len(chunks),
        n_chunks_dropped_short=dropped_short,
        n_chunks_dropped_low_alpha=dropped_alpha,
        n_chunks_cut_for_span=cut_for_span,
    )
    return chunks, stats


def verify_chunk_provenance(chunk: Chunk, pages: Sequence[Page]) -> bool:
    """True only if the chunk text re-derives exactly from the cited pages.

    Checks the stored hash and word count, that every cited page exists, and that the words
    appear contiguously with the first word on ``page_start`` and the last on ``page_end``.
    """
    target = chunk.text.split()
    if (
        chunk.page_start > chunk.page_end
        or len(target) != chunk.word_count
        or sha256_text(chunk.text) != chunk.text_sha256
    ):
        return False
    by_number = {page.page: page for page in pages}
    doc_words: list[str] = []
    word_pages: list[int] = []
    for number in range(chunk.page_start, chunk.page_end + 1):
        page = by_number.get(number)
        if page is None:
            return False
        page_words = normalize_text(page.text).split()
        doc_words.extend(page_words)
        word_pages.extend([number] * len(page_words))
    first, size = target[0], len(target)
    for i, word in enumerate(doc_words):
        if (
            word == first
            and doc_words[i : i + size] == target
            and word_pages[i] == chunk.page_start
            and word_pages[i + size - 1] == chunk.page_end
        ):
            return True
    return False