"""Demo snapshots: stored real-data runs served when demo mode is on.

A snapshot is a captured ``ScenarioDetail`` plus capture metadata, stored as
one JSON file per key. The default directory is the TRACKED
``demo/snapshots/`` (audited, citation-metadata only; see ``demo/README.md``),
so a fresh clone serves the demo with zero keys; point
``CLIMATEADAPT_DEMO_SNAPSHOTS_DIR`` elsewhere for private captures (see
``scripts/capture_demo_snapshot.py``). The API serves snapshots verbatim — the
UI labels them "cached real-data snapshot" with the capture timestamp, so a
demo works offline and under rate limits without ever presenting stored
results as live ones.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from climateadapt.api.schemas_scenarios import SCENARIO_API_VERSION, ScenarioDetail

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1
"""Snapshot file format version (rejected when it differs)."""

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
"""Allowed snapshot keys (also blocks path traversal: stems only)."""


class DemoSnapshotFile(BaseModel):
    """One snapshot file: capture metadata plus the stored detail."""

    model_config = ConfigDict(extra="forbid")

    snapshot_version: Literal[1] = SNAPSHOT_VERSION
    key: str = Field(pattern=KEY_PATTERN.pattern)
    label: str = Field(min_length=1, max_length=160)
    captured_at_utc: datetime
    detail: ScenarioDetail


class DemoSnapshotSummary(BaseModel):
    """List entry: identity and capture time, without the stored detail."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    captured_at_utc: datetime
    status: str
    scenario_id: str


class DemoSnapshotList(BaseModel):
    """Snapshot catalogue (versioned like the scenario contract)."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = SCENARIO_API_VERSION
    snapshots: list[DemoSnapshotSummary]


DEFAULT_SNAPSHOTS_DIR = Path("demo/snapshots")
"""Tracked fallback: audited snapshots shipped with the repo (P19)."""


def snapshots_dir(data_dir: Path, override: Path | None) -> Path:
    """Resolve the snapshot directory (explicit setting wins).

    ``data_dir`` is kept for call-site compatibility but no longer anchors the
    default: fresh clones serve the tracked ``demo/snapshots/``.
    """
    return override if override is not None else DEFAULT_SNAPSHOTS_DIR


def _read_snapshot(path: Path) -> DemoSnapshotFile | None:
    try:
        snapshot = DemoSnapshotFile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Skipping unreadable demo snapshot %s: %s", path.name, exc)
        return None
    if snapshot.key != path.stem:
        logger.warning(
            "Skipping demo snapshot %s: key %r does not match the filename.",
            path.name,
            snapshot.key,
        )
        return None
    return snapshot


def list_demo_snapshots(directory: Path) -> list[DemoSnapshotSummary]:
    """List valid snapshots by key. A missing dir or bad files yield less."""
    if not directory.is_dir():
        return []
    summaries: list[DemoSnapshotSummary] = []
    for path in sorted(directory.glob("*.json")):
        snapshot = _read_snapshot(path)
        if snapshot is None:
            continue
        summaries.append(
            DemoSnapshotSummary(
                key=snapshot.key,
                label=snapshot.label,
                captured_at_utc=snapshot.captured_at_utc,
                status=snapshot.detail.status,
                scenario_id=snapshot.detail.scenario_id,
            )
        )
    summaries.sort(key=lambda summary: summary.key)
    return summaries


def load_demo_snapshot(directory: Path, key: str) -> DemoSnapshotFile | None:
    """Load one snapshot by key, or None (unknown key, bad file, bad name)."""
    if not KEY_PATTERN.match(key):
        return None
    return _read_snapshot(directory / f"{key}.json")


def write_demo_snapshot(
    directory: Path, key: str, label: str, captured_at_utc: datetime,
    detail: ScenarioDetail,
) -> Path:
    """Write (or overwrite) one snapshot file; returns the path written."""
    if not KEY_PATTERN.match(key):
        raise ValueError(f"Invalid snapshot key: {key!r}")
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = DemoSnapshotFile(
        key=key,
        label=label,
        captured_at_utc=captured_at_utc,
        detail=detail,
    )
    path = directory / f"{key}.json"
    path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
