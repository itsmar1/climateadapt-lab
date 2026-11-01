"""Tests for vision.features (numpy only; always run, no network)."""

from __future__ import annotations

import numpy as np
import pytest

from climateadapt.vision.features import aggregate_mean_std, flatten


def _arrays() -> np.ndarray:
    """Two hand-checkable (12, 18) rows: all-ones + ramp-in-band-0."""
    arrays = np.zeros((2, 12, 18), dtype=np.float64)
    arrays[0] = 1.0
    arrays[1, :, 0] = np.arange(12, dtype=np.float64)
    arrays[1, :, 1:] = 2.0
    return arrays


def test_mean_std_values_and_shape():
    """Per-band mean then std, verified against hand-computed numbers."""
    out = aggregate_mean_std(_arrays())
    assert out.X.shape == (2, 36)
    assert out.kept == (0, 1)
    assert out.dropped == ()
    assert out.X[0, :18] == pytest.approx(np.ones(18))
    assert out.X[0, 18:] == pytest.approx(np.zeros(18))
    assert out.X[1, 0] == pytest.approx(5.5)
    assert out.X[1, 18] == pytest.approx(3.452052529534663)  # sqrt(143 / 12)
    assert out.X[1, 1:18] == pytest.approx(np.full(17, 2.0))
    assert out.X[1, 19:] == pytest.approx(np.zeros(17))


def test_partial_nan_uses_finite_timesteps_only():
    """One NaN timestep is excluded from that band's mean/std, not zeroed."""
    arrays = _arrays()
    arrays[1, 0, 0] = np.nan  # drop the 0.0 from band 0 -> values 1..11
    out = aggregate_mean_std(arrays)
    assert out.kept == (0, 1)
    assert out.dropped == ()
    assert out.X[1, 0] == pytest.approx(6.0)
    assert out.X[1, 18] == pytest.approx(3.1622776601683795)


def test_all_nan_band_excludes_row():
    """A row with a band lacking any finite timestep is dropped + reported."""
    arrays = _arrays()
    arrays[0, :, 5] = np.nan
    out = aggregate_mean_std(arrays)
    assert out.kept == (1,)
    assert out.dropped == (0,)
    assert out.X.shape == (1, 36)


def test_no_usable_rows_fails():
    """Aggregation refuses to invent features when nothing is usable."""
    arrays = np.full((2, 12, 18), np.nan)
    with pytest.raises(ValueError, match="no usable rows"):
        aggregate_mean_std(arrays)
    with pytest.raises(ValueError, match="no usable rows"):
        flatten(arrays)


def test_bad_shapes_fail():
    """Wrong timesteps/bands, wrong ndim and empty batches fail loudly."""
    with pytest.raises(ValueError, match="expected"):
        aggregate_mean_std(np.zeros((2, 12, 17)))
    with pytest.raises(ValueError, match="expected"):
        aggregate_mean_std(np.zeros((12, 18)))
    with pytest.raises(ValueError, match="no rows"):
        aggregate_mean_std(np.zeros((0, 12, 18)))
    with pytest.raises(ValueError, match="expected"):
        flatten(np.zeros((2, 6, 18)))


def test_flatten_values_and_exclusion():
    """Row-major flatten keeps NaN positions and the same exclusion rule."""
    arrays = _arrays()
    arrays[1, 3, 7] = np.nan  # partial gap stays NaN, row stays usable
    out = flatten(arrays)
    assert out.X.shape == (2, 216)
    assert out.kept == (0, 1)
    assert out.X[0] == pytest.approx(np.ones(216))
    assert np.isnan(out.X[1, 3 * 18 + 7])
    assert out.X[1, 0] == pytest.approx(0.0)
    assert out.X[1, 11 * 18] == pytest.approx(11.0)
