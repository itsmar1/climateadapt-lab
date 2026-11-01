"""Tests for vision.loader (pandas-free; h5py parts skip when missing)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from climateadapt.vision.loader import (
    aggregate_test_file,
    collect_train_paths,
    feature_filename,
    load_array,
    load_matrices,
    read_labels,
)


def _write_labels(path: Path) -> None:
    """Three rows: two train (one crop), one test non-crop."""
    features = []
    for index, dataset, is_crop, is_test in [
        (11, "kenya", True, False),
        (12, "kenya", False, False),
        (13, "togo-eval", False, True),
    ]:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [36.0, 0.5]},
            "properties": {
                "index": index,
                "is_crop": is_crop,
                "lat": 0.5,
                "lon": 36.0,
                "dataset": dataset,
                "collection_date": "2020-06-01",
                "export_end_date": "2021-02-01T00:00:00",
                "is_test": is_test,
            },
        })
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def test_read_labels_values_and_keys(tmp_path):
    """Rows parse with coerced types and unique index|dataset keys."""
    labels_path = tmp_path / "labels.geojson"
    _write_labels(labels_path)
    label_set = read_labels(labels_path)
    rows = label_set.rows
    assert label_set.excluded == ()
    assert len(rows) == 3
    assert rows[0].key == "11|kenya"
    assert rows[2].key == "13|togo-eval"
    assert rows[0].is_crop is True
    assert rows[2].is_test is True
    assert rows[1].label is None
    assert rows[0].lat == pytest.approx(0.5)


def test_read_labels_rejects_bad_files(tmp_path):
    """Non-collections, empty sets and all-invalid rows fail loudly."""
    bad = tmp_path / "bad.geojson"
    bad.write_text(json.dumps({"type": "Feature", "properties": {}}))
    with pytest.raises(ValueError, match="FeatureCollection"):
        read_labels(bad)
    bad.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    with pytest.raises(ValueError, match="no features"):
        read_labels(bad)
    bad.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"index": 1}}],
    }))
    with pytest.raises(ValueError, match="all 1 rows invalid"):
        read_labels(bad)


def test_read_labels_excludes_bad_rows_with_reasons(tmp_path):
    """One bad row is excluded (numbered + reasoned), the rest still load."""
    labels_path = tmp_path / "labels.geojson"
    _write_labels(labels_path)
    raw = json.loads(labels_path.read_text())
    raw["features"].append({"type": "Feature", "properties": {"index": 99}})
    raw["features"][0]["properties"]["lat"] = None
    labels_path.write_text(json.dumps(raw))
    label_set = read_labels(labels_path)
    assert len(label_set.rows) == 2
    assert [e.number for e in label_set.excluded] == [0, 3]
    assert "missing properties" in label_set.excluded[1].reason


def test_feature_filename_convention():
    """Per-row files follow {index}_{dataset}.h5."""
    assert feature_filename(11, "kenya") == "11_kenya.h5"


def test_collect_train_paths_excludes_test_and_counts_gaps(tmp_path):
    """Only non-test rows with files train; test-flagged files are counted out."""
    labels_path = tmp_path / "labels.geojson"
    _write_labels(labels_path)
    rows = read_labels(labels_path).rows
    features = tmp_path / "features"
    features.mkdir()
    (features / "11_kenya.h5").touch()
    # 12_kenya.h5 absent -> missing; the is_test row's file must NOT train.
    (features / "13_togo-eval.h5").touch()
    train = collect_train_paths(rows, features)
    assert [r.key for r, _ in train.entries] == ["11|kenya"]
    assert train.missing == 1
    assert train.test_flagged_with_files == 1


def test_load_array_needs_h5py(monkeypatch):
    """Without h5py the reader raises an install hint, not a bare ImportError."""
    monkeypatch.setitem(sys.modules, "h5py", None)
    with pytest.raises(ImportError, match="h5py"):
        load_array(Path("whatever.h5"))


def test_load_array_roundtrip_and_shape_guard(tmp_path):
    """Real .h5 round-trip works; wrong shapes and datasets fail loudly."""
    h5py = pytest.importorskip("h5py")
    good = tmp_path / "11_kenya.h5"
    with h5py.File(good, "w") as handle:
        handle["array"] = np.ones((12, 18), dtype=np.float32)
    assert load_array(good).shape == (12, 18)
    assert load_array(good).dtype == np.float64
    bad = tmp_path / "12_kenya.h5"
    with h5py.File(bad, "w") as handle:
        handle["array"] = np.ones((4, 4))
    with pytest.raises(ValueError, match=r"expected \(12, 18\)"):
        load_array(bad)
    empty = tmp_path / "13_x.h5"
    with h5py.File(empty, "w"):
        pass
    with pytest.raises(ValueError, match="no 'array'"):
        load_array(empty)


def test_load_matrices_stacks_and_labels(tmp_path):
    """Matrices stack to (n, 12, 18) with 1/0 labels + progress callback."""
    h5py = pytest.importorskip("h5py")
    labels_path = tmp_path / "labels.geojson"
    _write_labels(labels_path)
    rows = read_labels(labels_path).rows
    for row, value in [(rows[0], 3.0), (rows[1], 4.0)]:
        path = tmp_path / f"{row.index}_{row.dataset}.h5"
        with h5py.File(path, "w") as handle:
            handle["array"] = np.full((12, 18), value)
    entries = [
        (rows[0], tmp_path / "11_kenya.h5"),
        (rows[1], tmp_path / "12_kenya.h5"),
    ]
    seen: list[tuple[int, int]] = []
    matrices, labels = load_matrices(entries, progress=lambda d, t: seen.append((d, t)))
    assert matrices.shape == (2, 12, 18)
    assert matrices[0, 0, 0] == pytest.approx(3.0)
    assert labels.tolist() == [1, 0]
    assert seen[-1] == (2, 2)
    with pytest.raises(ValueError, match="no feature files"):
        load_matrices([])


def _write_grid(path: Path, y: np.ndarray, x: np.ndarray) -> None:
    """Write a consolidated test grid (keys x/y/lats/lons)."""
    import h5py

    with h5py.File(path, "w") as handle:
        handle["x"] = x
        handle["y"] = y
        handle["lats"] = np.zeros(len(y))
        handle["lons"] = np.zeros(len(y))


def test_aggregate_test_file_ignores_missing_and_drops_nonfinite(tmp_path):
    """y=-1 rows are ignored with a count; non-finite rows drop by position."""
    pytest.importorskip("h5py")
    grid_path = tmp_path / "probe.h5"
    x = np.ones((5, 12, 18), dtype=np.float64)
    x[3, :, 4] = np.nan  # evaluable row with a fully non-finite band
    _write_grid(grid_path, np.array([1, 0, -1, 0, 1]), x)
    out = aggregate_test_file(grid_path, kind="mean_std", chunk_rows=2)
    assert out.name == "probe"
    assert out.y.tolist() == [1, 0, 1]
    assert out.X.shape == (3, 36)
    assert out.n_ignored_missing == 1
    assert out.dropped == (2,)  # third evaluable row (position in y != -1 order)
    flat = aggregate_test_file(grid_path, kind="flatten", chunk_rows=2)
    assert flat.X.shape == (3, 216)
    assert flat.y.tolist() == [1, 0, 1]


def test_aggregate_test_file_rejects_bad_grids(tmp_path):
    """Bad kinds, shapes, keys, labels and empty grids fail loudly."""
    h5py = pytest.importorskip("h5py")
    grid_path = tmp_path / "probe.h5"
    _write_grid(grid_path, np.array([1, 0]), np.ones((2, 12, 18)))
    with pytest.raises(ValueError, match="unknown feature kind"):
        aggregate_test_file(grid_path, kind="median")
    with pytest.raises(ValueError, match="chunk_rows"):
        aggregate_test_file(grid_path, chunk_rows=0)
    bad = tmp_path / "bad.h5"
    _write_grid(bad, np.array([1, 2]), np.ones((2, 12, 18)))
    with pytest.raises(ValueError, match="outside"):
        aggregate_test_file(bad)
    with h5py.File(tmp_path / "shallow.h5", "w") as handle:
        handle["x"] = np.ones((2, 6, 18))
        handle["y"] = np.array([1, 0])
        handle["lats"] = np.zeros(2)
        handle["lons"] = np.zeros(2)
    with pytest.raises(ValueError, match=r"expected \('n', 12, 18\)"):
        aggregate_test_file(tmp_path / "shallow.h5")
    with h5py.File(tmp_path / "nokeys.h5", "w") as handle:
        handle["x"] = np.ones((1, 12, 18))
    with pytest.raises(ValueError, match="lacks"):
        aggregate_test_file(tmp_path / "nokeys.h5")
    _write_grid(tmp_path / "allmissing.h5", np.array([-1, -1]), np.ones((2, 12, 18)))
    with pytest.raises(ValueError, match="no evaluable rows"):
        aggregate_test_file(tmp_path / "allmissing.h5")
