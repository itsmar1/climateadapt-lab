"""Scenario persistence: a swappable store backed by stdlib SQLite.

``ScenarioStore`` is the interface the API depends on (SQLite today,
PostgreSQL tomorrow only if the owner asks — the seam is the protocol).
``SqliteScenarioStore`` keeps one row per scenario: the validated input, the
agent's terminal outputs (bundle, ranking, report, trace), status, problems,
and timestamps. Thread-safe (one locked connection, WAL mode) so worker
threads can write while request threads read.

Migrations are explicit and minimal: ``PRAGMA user_version`` tracks the schema
and ``_MIGRATIONS`` applies each version exactly once, oldest first.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
"""Current SQLite schema version (stored as ``PRAGMA user_version``)."""

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE IF NOT EXISTS scenarios (
            scenario_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL,
            scenario_json TEXT NOT NULL,
            bundle_json TEXT,
            ranking_json TEXT,
            report_json TEXT,
            trace_json TEXT,
            problems_json TEXT NOT NULL DEFAULT '[]',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_scenarios_created ON scenarios (created_at DESC)",
    ),
}

TERMINAL_STATUSES = frozenset({"complete", "partial", "failed"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ScenarioStore(Protocol):
    """Persistence seam for scenarios (SQLite now, swappable later)."""

    def create(self, scenario_id: str, job_id: str, scenario: dict[str, Any]) -> None: ...
    def set_job_id(self, scenario_id: str, job_id: str) -> None: ...
    def get(self, scenario_id: str) -> dict[str, Any] | None: ...
    def exists(self, scenario_id: str) -> bool: ...
    def mark_running(self, scenario_id: str) -> None: ...
    def save_result(
        self,
        scenario_id: str,
        *,
        status: str,
        bundle: dict[str, Any] | None,
        ranking: dict[str, Any] | None,
        report: dict[str, Any] | None,
        trace: dict[str, Any] | None,
        problems: list[str],
        warnings: list[str],
    ) -> None: ...
    def list_recent(self, limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]: ...
    def delete(self, scenario_id: str) -> bool: ...
    def close(self) -> None: ...


class SqliteScenarioStore:
    """Thread-safe SQLite implementation of ``ScenarioStore``."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._migrate_locked()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def schema_version(self) -> int:
        with self._lock:
            row = self._conn.execute("PRAGMA user_version").fetchone()
            return int(row[0])

    def _migrate_locked(self) -> None:
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        for target in sorted(_MIGRATIONS):
            if target <= version:
                continue
            for statement in _MIGRATIONS[target]:
                self._conn.execute(statement)
            self._conn.execute(f"PRAGMA user_version = {target}")
            logger.info("Scenario DB migrated to schema version %d", target)
        self._conn.commit()
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Scenario DB schema v{version} is newer than supported v{SCHEMA_VERSION}."
            )

    def create(self, scenario_id: str, job_id: str, scenario: dict[str, Any]) -> None:
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO scenarios (scenario_id, job_id, status, scenario_json,"
                " problems_json, warnings_json, created_at, updated_at)"
                " VALUES (?, ?, 'queued', ?, '[]', '[]', ?, ?)",
                (scenario_id, job_id, json.dumps(scenario), now, now),
            )
            self._conn.commit()

    def set_job_id(self, scenario_id: str, job_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE scenarios SET job_id = ?, updated_at = ? WHERE scenario_id = ?",
                (job_id, _now_iso(), scenario_id),
            )
            self._conn.commit()

    def get(self, scenario_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scenarios WHERE scenario_id = ?", (scenario_id,)
            ).fetchone()
            return _row_to_dict(row) if row is not None else None

    def exists(self, scenario_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM scenarios WHERE scenario_id = ?", (scenario_id,)
            ).fetchone()
            return row is not None

    def mark_running(self, scenario_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE scenarios SET status = 'running', updated_at = ?"
                " WHERE scenario_id = ? AND status = 'queued'",
                (_now_iso(), scenario_id),
            )
            self._conn.commit()

    def save_result(
        self,
        scenario_id: str,
        *,
        status: str,
        bundle: dict[str, Any] | None,
        ranking: dict[str, Any] | None,
        report: dict[str, Any] | None,
        trace: dict[str, Any] | None,
        problems: list[str],
        warnings: list[str],
    ) -> None:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"save_result needs a terminal status, got {status!r}.")
        with self._lock:
            self._conn.execute(
                "UPDATE scenarios SET status = ?, bundle_json = ?, ranking_json = ?,"
                " report_json = ?, trace_json = ?, problems_json = ?,"
                " warnings_json = ?, updated_at = ? WHERE scenario_id = ?",
                (
                    status,
                    json.dumps(bundle) if bundle is not None else None,
                    json.dumps(ranking) if ranking is not None else None,
                    json.dumps(report) if report is not None else None,
                    json.dumps(trace) if trace is not None else None,
                    json.dumps(problems),
                    json.dumps(warnings),
                    _now_iso(),
                    scenario_id,
                ),
            )
            self._conn.commit()

    def list_recent(self, limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]:
        with self._lock:
            total = int(self._conn.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0])
            rows = self._conn.execute(
                "SELECT * FROM scenarios ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return total, [_row_to_dict(row) for row in rows]

    def delete(self, scenario_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM scenarios WHERE scenario_id = ?", (scenario_id,)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # best-effort shutdown
                logger.exception("Error closing the scenario database.")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "scenario_id": row["scenario_id"],
        "job_id": row["job_id"],
        "status": row["status"],
        "scenario": json.loads(row["scenario_json"]),
        "bundle": json.loads(row["bundle_json"]) if row["bundle_json"] else None,
        "ranking": json.loads(row["ranking_json"]) if row["ranking_json"] else None,
        "report": json.loads(row["report_json"]) if row["report_json"] else None,
        "trace": json.loads(row["trace_json"]) if row["trace_json"] else None,
        "problems": json.loads(row["problems_json"]),
        "warnings": json.loads(row["warnings_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
