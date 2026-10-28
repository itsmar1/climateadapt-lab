"""Reciprocal Rank Fusion (Cormack, Clarke and Buettcher, 2009).

score(d) = sum over rankings of 1 / (k + rank_d). The conventional k = 60 is my recollection of
the original paper, not verified here; it is configurable and will be checked against this
project's own evaluation set rather than assumed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class FusedHit:
    chunk_id: str
    score: float
    ranks: dict[str, int]


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = DEFAULT_RRF_K,
    top_k: int | None = None,
) -> list[FusedHit]:
    """Fuse ranked id lists. Deterministic: ties break by chunk id."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be a positive integer, got {k!r}.")
    if top_k is not None and (isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1):
        raise ValueError(f"top_k must be a positive integer, got {top_k!r}.")

    contributions: dict[str, list[float]] = {}
    ranks: dict[str, dict[str, int]] = {}
    for source, ids in rankings.items():
        if len(set(ids)) != len(ids):
            raise ValueError(f"Ranking {source!r} contains duplicate ids.")
        for position, chunk_id in enumerate(ids, start=1):
            contributions.setdefault(chunk_id, []).append(1.0 / (k + position))
            ranks.setdefault(chunk_id, {})[source] = position

    fused = [
        FusedHit(chunk_id=cid, score=math.fsum(parts), ranks=ranks[cid])
        for cid, parts in contributions.items()
    ]
    fused.sort(key=lambda hit: (-hit.score, hit.chunk_id))
    return fused if top_k is None else fused[:top_k]