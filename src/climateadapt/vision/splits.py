"""Split utilities: deterministic train caps and leakage assertions."""

from __future__ import annotations

from collections.abc import Collection

import numpy as np


def capped_indices(n: int, max_n: int | None, seed: int) -> list[int]:
    """Deterministic ``max_n``-subset of ``range(n)`` (sorted positions).

    ``max_n=None`` (or ``>= n``) keeps everything. Used to time-box the
    training set; the seed is recorded in the run manifest.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    if max_n is not None and max_n < 1:
        raise ValueError(f"max_n must be >= 1 or None, got {max_n}")
    if max_n is None or max_n >= n:
        return list(range(n))
    rng = np.random.RandomState(seed)
    return sorted(int(i) for i in rng.permutation(n)[:max_n])


def assert_disjoint(train_keys: Collection[str], test_keys: Collection[str]) -> None:
    """Fail loudly if any ``index|dataset`` key sits in both splits."""
    overlap = sorted(set(train_keys) & set(test_keys))
    if overlap:
        shown = ", ".join(overlap[:5])
        raise ValueError(f"{len(overlap)} rows leak across splits (e.g. {shown})")
