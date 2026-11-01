"""Temporal aggregation of CropHarvest arrays (numpy only).

Each feature array is ``(timesteps, bands)``. Classical baselines consume
per-band summaries over time. Rows where a band has no finite timestep
are excluded and reported — never zero-filled or imputed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from climateadapt.vision.constants import N_BANDS, N_TIMESTEPS


@dataclass(frozen=True)
class Aggregated:
    """Aggregated design matrix plus kept/dropped row positions."""

    X: np.ndarray
    kept: tuple[int, ...]
    dropped: tuple[int, ...]


def _usable_rows(arrays: np.ndarray) -> np.ndarray:
    """Boolean mask: a row is usable iff every band has a finite timestep."""
    finite = np.isfinite(arrays)
    per_band_ok = finite.any(axis=1)
    return per_band_ok.all(axis=1)


def aggregate_mean_std(arrays: np.ndarray) -> Aggregated:
    """Per-band temporal mean + std -> ``(n, 2 * bands)`` (NaN-aware)."""
    arrays = np.asarray(arrays, dtype=np.float64)
    if arrays.ndim != 3 or arrays.shape[1:] != (N_TIMESTEPS, N_BANDS):
        expected = ("n", N_TIMESTEPS, N_BANDS)
        raise ValueError(f"expected {expected}, got {arrays.shape}")
    if arrays.shape[0] == 0:
        raise ValueError("no rows to aggregate")
    usable = _usable_rows(arrays)
    if not usable.any():
        raise ValueError("no usable rows: every row has a band without finite timesteps")
    with np.errstate(all="ignore"):
        means = np.nanmean(arrays[usable], axis=1)
        stds = np.nanstd(arrays[usable], axis=1)
    kept = tuple(int(i) for i in np.flatnonzero(usable))
    dropped = tuple(int(i) for i in np.flatnonzero(~usable))
    return Aggregated(X=np.concatenate([means, stds], axis=1), kept=kept, dropped=dropped)


def flatten(arrays: np.ndarray) -> Aggregated:
    """Flatten time x bands -> ``(n, timesteps * bands)``.

    Same exclusion rule as :func:`aggregate_mean_std`: rows with a fully
    non-finite band are dropped. Remaining NaNs (partially missing
    timesteps) are preserved as NaN in the output.
    """
    arrays = np.asarray(arrays, dtype=np.float64)
    if arrays.ndim != 3 or arrays.shape[1:] != (N_TIMESTEPS, N_BANDS):
        expected = ("n", N_TIMESTEPS, N_BANDS)
        raise ValueError(f"expected {expected}, got {arrays.shape}")
    if arrays.shape[0] == 0:
        raise ValueError("no rows to flatten")
    usable = _usable_rows(arrays)
    if not usable.any():
        raise ValueError("no usable rows: every row has a band without finite timesteps")
    kept = tuple(int(i) for i in np.flatnonzero(usable))
    dropped = tuple(int(i) for i in np.flatnonzero(~usable))
    return Aggregated(X=arrays[usable].reshape(int(usable.sum()), -1), kept=kept, dropped=dropped)
