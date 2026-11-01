"""Tests for vision.report (stdlib; always run, no network)."""

from __future__ import annotations

import json

from climateadapt.vision.constants import BAND_NAMES
from climateadapt.vision.report import (
    LIMITATIONS,
    assemble_manifest,
    package_version,
    write_manifest,
)


def _manifest(**overrides):
    """Minimal manifest with overridable fields."""
    base = {
        "model": "logreg",
        "seed": 42,
        "feature_kind": "mean_std",
        "n_train_rows": 100,
        "n_test_rows": 20,
        "train_capped": False,
        "files": {"labels.geojson": {"size": 1, "md5": "x", "md5_match": True}},
        "evaluation": {"accuracy": 0.8},
        "confidence_intervals": {"accuracy": {"lo": 0.7, "hi": 0.9}},
        "exclusions": {"missing_train_files": 0},
        "run_id": "abc123",
    }
    base.update(overrides)
    return assemble_manifest(**base)


def test_manifest_carries_provenance_and_limits():
    """Dataset DOI/licence/citation, bands and the can/cannot limits persist."""
    manifest = _manifest()
    dataset = manifest["dataset"]
    assert dataset["doi"] == "10.5281/zenodo.10251170"
    assert dataset["version_id"] == 10251170
    assert dataset["licence_spdx"] == "CC-BY-SA-4.0"
    assert "tseng" in dataset["citation_key"]
    assert manifest["bands"] == list(BAND_NAMES)
    assert len(manifest["bands"]) == 18
    assert manifest["n_timesteps"] == 12
    assert manifest["limitations"] == list(LIMITATIONS)
    assert any("drought" in line for line in manifest["limitations"])
    assert manifest["mlflow_run_id"] == "abc123"
    assert manifest["package_versions"]["numpy"] != "not-installed"


def test_manifest_json_roundtrip_creates_parents(tmp_path):
    """Manifests serialize to JSON, creating missing directories."""
    path = tmp_path / "deep" / "nested" / "run.json"
    written = write_manifest(path, _manifest())
    assert written == path
    assert json.loads(path.read_text(encoding="utf-8"))["model"] == "logreg"


def test_package_version_marks_missing():
    """Installed distributions report versions; absent ones stay explicit."""
    assert package_version("numpy") not in ("", "not-installed")
    assert package_version("no-such-distribution-xyz") == "not-installed"
