"""Catalog loading: the packaged catalog.json or an explicit file (offline)."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from climateadapt.recommend.schema import InterventionCatalog


def packaged_catalog_path() -> Path:
    """Path of the versioned catalog shipped with this package."""
    return Path(str(resources.files("climateadapt.recommend") / "catalog.json"))


def load_catalog(path: Path | None = None) -> InterventionCatalog:
    """Load and validate a catalog (default: the packaged catalog)."""
    text = (path or packaged_catalog_path()).read_text(encoding="utf-8")
    return InterventionCatalog.model_validate_json(text)
