"""Run-manifest assembly (stdlib only): everything behind a metric."""

from __future__ import annotations

import json
from importlib import metadata as _metadata
from pathlib import Path
from typing import Any

from climateadapt.vision.constants import (
    BAND_NAMES,
    CITATION_AUTHORS,
    CITATION_KEY,
    CITATION_TITLE,
    CITATION_URL,
    CITATION_VENUE,
    DATASET_CONCEPT_DOI,
    DATASET_DOI,
    DATASET_URL,
    DATASET_VERSION_ID,
    DATASET_VERSION_LABEL,
    LICENCE_SPDX,
    LICENCE_URL,
    N_BANDS,
    N_TIMESTEPS,
)

LIMITATIONS: tuple[str, ...] = (
    "Crop/non-crop classification only: the model says nothing about drought, "
    "yield, crop health, or whether any adaptation intervention works.",
    "Training and test rows come from 21 constituent label datasets with "
    "uneven geography and years; performance elsewhere is unmeasured.",
    "Only rows with processed features are used; rows without features are "
    "excluded and counted, which can bias the sample.",
    "Aggregated per-band statistics discard temporal order and spatial "
    "context beyond the single pixel/field footprint.",
)


def package_version(name: str) -> str:
    """Installed distribution version, or ``"not-installed"``."""
    try:
        return _metadata.version(name)
    except _metadata.PackageNotFoundError:
        return "not-installed"


def assemble_manifest(
    *,
    model: str,
    seed: int,
    feature_kind: str,
    n_train_rows: int,
    n_test_rows: int,
    train_capped: bool,
    files: dict[str, dict[str, Any]],
    evaluation: dict[str, Any],
    confidence_intervals: dict[str, dict[str, float]],
    exclusions: dict[str, Any],
    run_id: str | None,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON-serializable manifest stored per run."""
    return {
        "task": "binary crop/non-crop (CropHarvest is_crop)",
        "dataset": {
            "name": "CropHarvest",
            "version_id": DATASET_VERSION_ID,
            "version_label": DATASET_VERSION_LABEL,
            "doi": DATASET_DOI,
            "concept_doi": DATASET_CONCEPT_DOI,
            "url": DATASET_URL,
            "licence_spdx": LICENCE_SPDX,
            "licence_url": LICENCE_URL,
            "citation_key": CITATION_KEY,
            "citation_title": CITATION_TITLE,
            "citation_authors": CITATION_AUTHORS,
            "citation_venue": CITATION_VENUE,
            "citation_url": CITATION_URL,
            "files": files,
        },
        "bands": list(BAND_NAMES),
        "n_timesteps": N_TIMESTEPS,
        "n_bands": N_BANDS,
        "model": model,
        "seed": seed,
        "feature_kind": feature_kind,
        "n_train_rows": n_train_rows,
        "n_test_rows": n_test_rows,
        "train_capped": train_capped,
        "exclusions": exclusions,
        "evaluation": evaluation,
        "confidence_intervals": confidence_intervals,
        "mlflow_run_id": run_id,
        "extra_params": extra_params or {},
        "limitations": list(LIMITATIONS),
        "package_versions": {
            name: package_version(name)
            for name in ("numpy", "scikit-learn", "h5py", "mlflow", "climateadapt-lab")
        },
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    """Write the manifest as indented JSON (creating parent dirs)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path
