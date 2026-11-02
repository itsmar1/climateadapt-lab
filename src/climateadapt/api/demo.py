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


EVIDENCE_METADATA_KEYS = frozenset(
    {
        "chunk_id",
        "citation",
        "doc_id",
        "landing_url",
        "license",
        "license_status",
        "pages",
    }
)
"""Evidence items are citation metadata only: no text/excerpt field may exist."""

_LOCAL_PATH_RES = (
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"/home/"),
    re.compile(r"/Users/"),
    re.compile(r"data/corpus"),
    re.compile(r"data/cache"),
    re.compile(r"data/demo"),
    re.compile(r"\.cdsapirc", re.IGNORECASE),
    re.compile(r"(^|[\s\"'=])\.env(\s|$|\"|')"),
    re.compile(r"\.sqlite3?(-wal|-shm)?", re.IGNORECASE),
)

_SECRET_RES = (
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"Authorization:\s*Bearer", re.IGNORECASE),
    re.compile(r"BEGIN\s+[A-Z ]*PRIVATE\s+KEY"),
    re.compile(r"\bsk-[A-Za-z0-9]{8,}"),
)

_ADDRESS_RES = (
    re.compile(r"127\.0\.0\.1"),
    re.compile(r"localhost", re.IGNORECASE),
    re.compile(r"\b0\.0\.0\.0\b"),
    re.compile(r"\b192\.168\.\d+\.\d+"),
    re.compile(r"\b10\.\d+\.\d+\.\d+"),
    re.compile(r"Failed to connect to", re.IGNORECASE),
    re.compile(r"CURL error", re.IGNORECASE),
)

_CORPUS_KEY_RES = (
    re.compile(r"\"passage_text\"\s*:"),
    re.compile(r"\"chunk_text\"\s*:"),
    re.compile(r"\"excerpt\"\s*:"),
)


def audit_demo_snapshot(snapshot: DemoSnapshotFile) -> list[str]:
    """Pre-commit audit for one snapshot (P19 rules, P25 guard).

    Returns human-readable problems; empty means the snapshot may be tracked.
    Checks: evidence items carry citation metadata only (no passage text,
    values under 600 chars); the trace keeps no raw draft/repair text; no
    local paths, secrets, key material, or proxy/local addresses anywhere;
    every computed indicator and evidence item carries provenance/licence
    fields.
    """
    problems: list[str] = []
    dumped = snapshot.model_dump(mode="json")
    detail = dumped.get("detail") or {}
    report = detail.get("report") or {}
    for index, item in enumerate(report.get("evidence") or []):
        if set(item) != EVIDENCE_METADATA_KEYS:
            problems.append(
                f"evidence[{index}] keys {sorted(item)} are not citation metadata only"
            )
        for field, value in item.items():
            if len(str(value)) >= 600:
                problems.append(f"evidence[{index}].{field} is {len(str(value))} chars")
    trace = detail.get("trace") or {}
    if trace.get("draft_text"):
        problems.append("trace keeps draft_text (strip raw model output)")
    if trace.get("repair_text"):
        problems.append("trace keeps repair_text (strip raw model output)")
    bundle = detail.get("bundle") or {}
    for entry in bundle.get("entries") or []:
        if entry.get("status") != "ok":
            continue
        result = entry.get("result") or {}
        for field in ("citation", "license_note", "data_source", "doi"):
            if not result.get(field):
                problems.append(f"bundle {entry.get('indicator')}: missing {field}")
    for index, item in enumerate(report.get("evidence") or []):
        for field in ("citation", "license", "pages", "landing_url"):
            if not item.get(field):
                problems.append(f"evidence[{index}]: missing {field}")
    raw = json.dumps(dumped, sort_keys=True)
    for pattern in _LOCAL_PATH_RES:
        if pattern.search(raw):
            problems.append(f"local path or cache reference: {pattern.pattern}")
    for pattern in _SECRET_RES:
        if pattern.search(raw):
            problems.append(f"possible secret or key material: {pattern.pattern}")
    for pattern in _ADDRESS_RES:
        if pattern.search(raw):
            problems.append(f"proxy or local address: {pattern.pattern}")
    for pattern in _CORPUS_KEY_RES:
        if pattern.search(raw):
            problems.append(f"corpus text key present: {pattern.pattern}")
    return problems
