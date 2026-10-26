"""Provenance record stored next to every cached file."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Provenance(BaseModel):
    """Where a cached file came from, when, and its integrity fingerprint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset: str
    version: str
    product: Literal["final"]
    variable: str
    units: str
    temporal_resolution: Literal["monthly"]
    year: int
    month: int
    source_url: str
    retrieved_at_utc: datetime
    sha256: str
    size_bytes: int
    cache_path: str
    citation: str
    doi: str
    license_note: str