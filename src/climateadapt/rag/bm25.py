"""BM25 (Okapi, Lucene-style idf) over chunks, implemented here so it is small and testable.

score(q, d) = sum over unique query terms t of
    idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg_len))
    idf(t)  = ln(1 + (N - n_t + 0.5) / (n_t + 0.5))   (always positive)

No stemming and no stop-word list: both are language specific, and idf already down-weights
common words. Tokens are Unicode letters/digits, case-folded.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from climateadapt.rag.models import Chunk

_TOKEN = re.compile(r"[^\W_]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).casefold())


class BM25Index:
    def __init__(self, chunks: Sequence[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 < 0 or not 0.0 <= b <= 1.0:
            raise ValueError("Require k1 >= 0 and 0 <= b <= 1.")
        self._chunks = list(chunks)
        self._k1 = k1
        self._b = b
        self._lengths: list[int] = []
        self._postings: dict[str, list[tuple[int, int]]] = {}
        for position, chunk in enumerate(self._chunks):
            counts = Counter(tokenize(chunk.text))
            self._lengths.append(sum(counts.values()))
            for term, tf in counts.items():
                self._postings.setdefault(term, []).append((position, tf))
        self._avg_length = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0

    @property
    def chunks(self) -> list[Chunk]:
        return self._chunks

    def idf(self, term: str) -> float:
        n_docs = len(self._chunks)
        n_term = len(self._postings.get(term, ()))
        return math.log(1.0 + (n_docs - n_term + 0.5) / (n_term + 0.5))

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """Return (chunk position, score) pairs, best first; ties break by position."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        scores: dict[int, float] = {}
        for term in dict.fromkeys(tokenize(query)):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self.idf(term)
            for position, tf in postings:
                norm = 1.0 - self._b + self._b * self._lengths[position] / self._avg_length
                scores[position] = scores.get(position, 0.0) + idf * tf * (self._k1 + 1.0) / (
                    tf + self._k1 * norm
                )
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:top_k]