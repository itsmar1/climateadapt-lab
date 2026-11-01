"""Tests for vision.splits (stdlib + numpy; always run, no network)."""

from __future__ import annotations

import numpy as np
import pytest

from climateadapt.vision.splits import assert_disjoint, capped_indices


def test_cap_none_and_oversize_keep_everything():
    """No cap (or a cap above n) returns every position in order."""
    assert capped_indices(5, None, seed=7) == [0, 1, 2, 3, 4]
    assert capped_indices(5, 5, seed=7) == [0, 1, 2, 3, 4]
    assert capped_indices(5, 99, seed=7) == [0, 1, 2, 3, 4]
    assert capped_indices(0, None, seed=7) == []


def test_cap_is_deterministic_and_valid():
    """Same seed twice gives the same sorted subset of range(n)."""
    first = capped_indices(10, 3, seed=7)
    second = capped_indices(10, 3, seed=7)
    assert first == second
    assert len(first) == 3
    assert first == sorted(first)
    assert all(0 <= i < 10 for i in first)
    # Matches an explicit seeded permutation (not just self-consistent).
    expected = sorted(int(i) for i in np.random.RandomState(7).permutation(10)[:3])
    assert first == expected


def test_bad_cap_arguments_fail():
    """Zero/negative caps and negative n fail loudly."""
    with pytest.raises(ValueError, match="max_n"):
        capped_indices(10, 0, seed=1)
    with pytest.raises(ValueError, match="max_n"):
        capped_indices(10, -2, seed=1)
    with pytest.raises(ValueError, match="n must be"):
        capped_indices(-1, None, seed=1)


def test_disjoint_passes_and_overlap_reports():
    """Disjoint key sets pass; any shared key fails with count + example."""
    assert_disjoint(["1|a", "2|a"], ["3|b"])
    with pytest.raises(ValueError, match="2 rows leak.*1\\|a") as excinfo:
        assert_disjoint(["1|a", "2|a"], ["2|a", "1|a", "9|z"])
    assert "2|a" in str(excinfo.value)
