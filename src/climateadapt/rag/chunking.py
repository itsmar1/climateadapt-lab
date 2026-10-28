"""Page-aware sliding-window chunking with verifiable provenance.

Chunks are windows of ``chunk_words`` words over the whole document, so a chunk may span a page
boundary; it records the page of its first and last word. Low-letter-ratio windows (mostly
numbers, for example tables) and tiny documents are DROPPED AND COUNTED, never silently lost.
``chunk_index`` counts windows including dropped ones, so gaps are visible.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from climateadapt.rag.models import Chunk, Page, make_chunk_id
from climateadapt.rag.text import normalize_text, words


@dataclass(frozen=True)
class ChunkingParams:
    chunk_words: int = 220
    overlap_words: int = 40
    min_words: int = 30
    min_alpha_ratio: float = 0.45

    def __post_init__(self) -> None:
        if self.chunk_words < 20:
            raise ValueError("chunk_words must be at least 20.")
        if not 0 <= self.overlap_words < self.chunk_words:
            raise ValueError("overlap_words must be >= 0 and smaller than chunk_words.")
        if not 1 <= self.min_words <= self.chunk_words:
            raise ValueError("min_words must be between 1 and chunk_words.")
        if not 0.0 <= self.min_alpha_ratio <= 1.0:
            raise ValueError("min_alpha_ratio must be between 0 and 1.")


@dataclass(frozen=True)
class ChunkingStats:
    n_pages: int
    n_empty_pages: int
    n_words: int
    n_chunks_kept: int
    n_chunks_dropped_short: int
    n_chunks_dropped_low_alpha: int


def _alpha_ratio(text: str) -> float:
    non_space = sum(1 for ch in text if not ch.isspace())
    if non_space == 0:
        return 0.0
    return sum(1 for ch in text if ch.isalpha()) / non_space


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_document(
    doc_id: str, 
    pages: Sequence[Page], 
    params: ChunkingParams = ChunkingParams()
) -> tuple[list[Chunk], ChunkingStats]:
    all_words: list[str] = []
    word_pages: list[int] = []
    n_empty = 0
    for page in pages:
        page_words = words(page.text)
        if not page_words:
            n_empty += 1
        all_words.extend(page_words)
        word_pages.extend([page.page] * len(page_words))

    total = len(all_words)
    step = params.chunk_words - params.overlap_words
    chunks: list[Chunk] = []
    dropped_short = dropped_alpha = 0
    start = index = 0
    while start < total:
        end = min(start + params.chunk_words, total)
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