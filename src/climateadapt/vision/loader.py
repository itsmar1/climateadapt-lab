"""Minimal CropHarvest-data loader (stdlib + numpy; ``h5py`` only for reads).

Labels are parsed with the standard library (no ``geopandas``): a
``labels.geojson`` row becomes a :class:`LabelRow`. Training rows resolve
to per-row ``{index}_{dataset}.h5`` files under ``features/``; rows
without a file are counted as missing, never imputed.

Official test data has a different layout: consolidated per-region files
under ``test_features/`` holding ``x`` ``(n, 12, 18)``, ``y`` in
``{-1, 0, 1}`` (``-1`` = ``MISSING_DATA``, excluded like upstream),
``lats`` and ``lons``. :func:`aggregate_test_file` streams those in
chunks so the ~1.4M-row grids never sit in RAM at once.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from climateadapt.vision import features as vf
from climateadapt.vision.constants import H5_DATASET, N_BANDS, N_TIMESTEPS

MISSING_LABEL = -1
TEST_GRID_KEYS: tuple[str, ...] = ("x", "y", "lats", "lons")

REQUIRED_PROPERTIES: tuple[str, ...] = (
    "index",
    "is_crop",
    "lat",
    "lon",
    "dataset",
    "collection_date",
    "export_end_date",
    "is_test",
)


@dataclass(frozen=True)
class LabelRow:
    """One validated ``labels.geojson`` feature (geometry not retained)."""

    index: int
    dataset: str
    is_crop: bool
    is_test: bool
    lat: float
    lon: float
    collection_date: str
    export_end_date: str
    label: str | None
    classification_label: str | None

    @property
    def key(self) -> str:
        """Unique ``index|dataset`` identity used for leakage checks."""
        return f"{self.index}|{self.dataset}"


@dataclass(frozen=True)
class ExcludedRow:
    """A label row skipped for a documented reason (never imputed)."""

    number: int
    reason: str


@dataclass(frozen=True)
class LabelSet:
    """Validated label rows plus excluded-row accounting."""

    rows: tuple[LabelRow, ...]
    excluded: tuple[ExcludedRow, ...]


@dataclass(frozen=True)
class TrainPaths:
    """Resolved training files plus missing-file accounting."""

    entries: tuple[tuple[LabelRow, Path], ...]
    missing: int
    test_flagged_with_files: int


@dataclass(frozen=True)
class TestAggregated:
    """One aggregated official test grid (``y == -1`` already excluded)."""

    name: str
    X: np.ndarray
    y: np.ndarray
    n_ignored_missing: int
    dropped: tuple[int, ...]


def _coerce_row(number: int, props: dict) -> LabelRow:
    missing = [name for name in REQUIRED_PROPERTIES if name not in props]
    if missing:
        raise ValueError(f"feature {number}: missing properties {missing}")
    try:
        return LabelRow(
            index=int(props["index"]),
            dataset=str(props["dataset"]),
            is_crop=bool(props["is_crop"]),
            is_test=bool(props["is_test"]),
            lat=float(props["lat"]),
            lon=float(props["lon"]),
            collection_date=str(props["collection_date"]),
            export_end_date=str(props["export_end_date"]),
            label=props.get("label"),
            classification_label=props.get("classification_label"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"feature {number}: bad property types ({exc})") from exc


def read_labels(path: Path) -> LabelSet:
    """Parse ``labels.geojson``; invalid rows are excluded with reasons."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        raise ValueError(f"{path}: expected a GeoJSON FeatureCollection")
    features = raw.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"{path}: FeatureCollection holds no features")
    rows: list[LabelRow] = []
    excluded: list[ExcludedRow] = []
    for number, feature in enumerate(features):
        props = feature.get("properties", {}) if isinstance(feature, dict) else {}
        try:
            rows.append(_coerce_row(number, props))
        except ValueError as exc:
            excluded.append(ExcludedRow(number, str(exc)))
    if not rows:
        raise ValueError(f"{path}: all {len(features)} rows invalid")
    return LabelSet(rows=tuple(rows), excluded=tuple(excluded))


def feature_filename(index: int, dataset: str) -> str:
    """Official per-row feature name: ``{index}_{dataset}.h5``."""
    return f"{index}_{dataset}.h5"


def collect_train_paths(
    rows: list[LabelRow] | tuple[LabelRow, ...],
    features_dir: Path,
) -> TrainPaths:
    """Match non-test rows to per-row files; ``is_test`` rows never train."""
    entries: list[tuple[LabelRow, Path]] = []
    missing = 0
    flagged = 0
    for row in rows:
        candidate = features_dir / feature_filename(row.index, row.dataset)
        if row.is_test:
            if candidate.is_file():
                flagged += 1
            continue
        if candidate.is_file():
            entries.append((row, candidate))
        else:
            missing += 1
    return TrainPaths(entries=tuple(entries), missing=missing, test_flagged_with_files=flagged)


def aggregate_test_file(
    path: Path,
    kind: str = "mean_std",
    chunk_rows: int = 50000,
) -> TestAggregated:
    """Aggregate one official test grid, streaming in chunks.

    Rows with ``y == -1`` (upstream ``MISSING_DATA``) are ignored with a
    count; evaluable rows with a fully non-finite band are dropped via
    :mod:`features` and reported by position.
    """
    if kind not in ("mean_std", "flatten"):
        raise ValueError(f"unknown feature kind {kind!r}")
    if chunk_rows < 1:
        raise ValueError(f"chunk_rows must be >= 1, got {chunk_rows}")
    try:
        import h5py
    except ImportError as exc:
        raise ImportError(
            "h5py is required to read CropHarvest feature files "
            "(install the P16 vision tools; see docs/VISION_BASELINE.md)"
        ) from exc
    aggregate = vf.aggregate_mean_std if kind == "mean_std" else vf.flatten
    Xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    dropped: list[int] = []
    ignored = 0
    offset = 0
    with h5py.File(path, "r") as handle:
        missing_keys = [key for key in TEST_GRID_KEYS if key not in handle]
        if missing_keys:
            raise ValueError(f"{path}: test grid lacks {missing_keys}")
        x, y = handle["x"], handle["y"]
        if x.ndim != 3 or x.shape[1:] != (N_TIMESTEPS, N_BANDS):
            expected = ("n", N_TIMESTEPS, N_BANDS)
            raise ValueError(f"{path}: expected {expected}, got {x.shape}")
        if len(y) != len(x) or len(handle["lats"]) != len(x) or len(handle["lons"]) != len(x):
            raise ValueError(f"{path}: y/lats/lons lengths disagree with x")
        labels = np.asarray(y)
        if set(np.unique(labels)) - {-1, 0, 1}:
            raise ValueError(f"{path}: y holds values outside {{-1, 0, 1}}")
        total = len(x)
        for start in range(0, total, chunk_rows):
            stop = min(start + chunk_rows, total)
            chunk_y = labels[start:stop]
            mask = chunk_y != MISSING_LABEL
            ignored += int((~mask).sum())
            if not mask.any():
                continue
            chunk_x = np.asarray(x[start:stop][mask], dtype=np.float64)
            try:
                agg = aggregate(chunk_x)
            except ValueError:
                dropped.extend(range(offset, offset + int(mask.sum())))
                offset += int(mask.sum())
                continue
            Xs.append(agg.X)
            ys.append(chunk_y[mask][list(agg.kept)])
            dropped.extend(offset + i for i in agg.dropped)
            offset += int(mask.sum())
    if not Xs:
        raise ValueError(f"{path}: no evaluable rows (all y == -1 or non-finite)")
    return TestAggregated(
        name=Path(path).stem,
        X=np.concatenate(Xs),
        y=np.concatenate(ys),
        n_ignored_missing=ignored,
        dropped=tuple(dropped),
    )


def load_array(path: Path) -> np.ndarray:
    """Read one ``(12, 18)`` feature array; any shape mismatch fails loudly."""
    try:
        import h5py
    except ImportError as exc:
        raise ImportError(
            "h5py is required to read CropHarvest feature files "
            "(install the P16 vision tools; see docs/VISION_BASELINE.md)"
        ) from exc
    with h5py.File(path, "r") as handle:
        if H5_DATASET not in handle:
            raise ValueError(f"{path}: no {H5_DATASET!r} dataset in file")
        array = np.asarray(handle[H5_DATASET], dtype=np.float64)
    if array.ndim != 2 or array.shape != (N_TIMESTEPS, N_BANDS):
        raise ValueError(f"{path}: expected {(N_TIMESTEPS, N_BANDS)}, got {array.shape}")
    return array


def load_matrices(
    entries: list[tuple[LabelRow, Path]],
    progress: Callable[[int, int], None] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Stack feature arrays to ``(n, 12, 18)`` with labels (1 = crop).

    ``progress``, when given, is called as ``progress(done, total)``
    after each file so CLIs can print incremental status.
    """
    if not entries:
        raise ValueError("no feature files to load")
    arrays = []
    for done, (_, path) in enumerate(entries, start=1):
        arrays.append(load_array(path))
        if progress is not None:
            progress(done, len(entries))
    labels = np.array([1 if row.is_crop else 0 for row, _ in entries], dtype=np.int64)
    return np.stack(arrays), labels
