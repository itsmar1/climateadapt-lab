"""Provenance record stored next to every cached CHIRPS file or remote point read."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Provenance(BaseModel):
    """Where data came from, when, and how it can be identified again.

    ``access_mode='download'``: the whole file was downloaded; ``sha256`` and ``size_bytes``
    describe the local copy. ``access_mode='remote_range_read'``: only one pixel was read;
    ``sha256`` is unavailable and the remote file is identified by the server-reported
    size, ETag, and Last-Modified (each may be None if the server did not provide them).
    """

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
    sha256: str | None = None
    size_bytes: int | None = None
    cache_path: str | None = None
    citation: str
    doi: str
    license_note: str
    access_mode: Literal["download", "remote_range_read"] = "download"
    remote_etag: str | None = None
    remote_last_modified: str | None = None