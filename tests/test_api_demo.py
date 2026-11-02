"""Tests for demo snapshots: store functions, route handlers, HTTP surface.

Store-level and route-level tests run anywhere (no sockets). The TestClient
HTTP tests follow the repo convention and run wherever sockets work.
No network, no credentials anywhere in this file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from climateadapt.api.demo import (
    DEFAULT_SNAPSHOTS_DIR,
    DemoSnapshotFile,
    DemoSnapshotList,
    audit_demo_snapshot,
    list_demo_snapshots,
    load_demo_snapshot,
    snapshots_dir,
    write_demo_snapshot,
)
from climateadapt.api.main import create_app
from climateadapt.api.scenarios import to_detail
from climateadapt.api.store import SqliteScenarioStore
from climateadapt.config import Settings, get_settings
from test_integration_workflow import make_deps, make_scenario, run_job, stub_bundle

CAPTURED = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)


def write_sample(tmp_path, monkeypatch, *, key="demo-1", label="Sample snapshot"):
    """Capture a real fallback detail through the integration path, store it."""
    deps = make_deps()
    stub_bundle(monkeypatch)
    db = SqliteScenarioStore(tmp_path / "db.sqlite3")
    scenario = make_scenario()
    db.create("sc-demo-1", "job-demo-1", scenario.model_dump(mode="json"))
    from climateadapt.api.dependencies import UnavailableProvider

    outcome = run_job(db, "sc-demo-1", deps, UnavailableProvider())
    assert outcome["status"] == "partial"
    row = db.get("sc-demo-1")
    assert row is not None
    snapshot = write_demo_snapshot(
        tmp_path / "snapshots", key, label, CAPTURED, to_detail(row)
    )
    db.close()
    return snapshot


def endpoint_for(app, path):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint
    raise AssertionError(f"no route for {path}")


def error_body(response) -> tuple[int, str]:
    payload = json.loads(response.body.decode("utf-8"))
    return response.status_code, payload["detail"][0]["type"]


# --- Store functions (run everywhere) ----------------------------------------


def test_write_list_load_roundtrip(tmp_path, monkeypatch):
    snapshot = write_sample(tmp_path, monkeypatch, key="demo-1")
    assert snapshot.name == "demo-1.json"

    summaries = list_demo_snapshots(tmp_path / "snapshots")
    assert len(summaries) == 1
    assert summaries[0].key == "demo-1"
    assert summaries[0].label == "Sample snapshot"
    assert summaries[0].captured_at_utc == CAPTURED
    assert summaries[0].status == "partial"
    assert summaries[0].scenario_id == "sc-demo-1"

    loaded = load_demo_snapshot(tmp_path / "snapshots", "demo-1")
    assert loaded is not None
    assert loaded.detail.report is not None
    assert loaded.detail.report.fallback is True


def test_missing_directory_lists_empty_and_loads_nothing(tmp_path):
    assert list_demo_snapshots(tmp_path / "absent") == []
    assert load_demo_snapshot(tmp_path / "absent", "demo-1") is None


def test_invalid_files_are_skipped(tmp_path, monkeypatch):
    directory = tmp_path / "snapshots"
    write_sample(tmp_path, monkeypatch, key="good")
    (directory / "broken.json").write_text("{not json", encoding="utf-8")
    (directory / "mismatch.json").write_text(
        json.dumps(
            {
                "snapshot_version": 1,
                "key": "other-key",
                "label": "x",
                "captured_at_utc": CAPTURED.isoformat(),
                "detail": None,
            }
        ),
        encoding="utf-8",
    )
    assert [s.key for s in list_demo_snapshots(directory)] == ["good"]
    assert load_demo_snapshot(directory, "broken") is None
    assert load_demo_snapshot(directory, "mismatch") is None


def test_traversal_and_bad_keys_rejected(tmp_path, monkeypatch):
    directory = tmp_path / "snapshots"
    write_sample(tmp_path, monkeypatch, key="good")
    for key in ("../escape", "a/b", "", "has space", "dot.json"):
        assert load_demo_snapshot(directory, key) is None
    with pytest.raises(ValueError, match="Invalid snapshot key"):
        write_demo_snapshot(
            directory, "../escape", "x", CAPTURED,
            load_demo_snapshot(directory, "good").detail,
        )
    assert not (tmp_path / "escape.json").exists()


# --- Tracked fallback directory (P19; run everywhere) ------------------------


ROOT = Path(__file__).resolve().parents[1]

TRACKED_SNAPSHOT_KEYS = frozenset(
    {
        "reference-morocco",
        "reference-morocco-ai",
        "trondelag-norway",
        "atlantic-ocean",
    }
)
"""Audited keys shipped in demo/snapshots/ (see demo/README.md)."""

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


def test_default_snapshots_dir_is_the_tracked_fallback(tmp_path):
    assert snapshots_dir(tmp_path / "data", None) == DEFAULT_SNAPSHOTS_DIR
    assert DEFAULT_SNAPSHOTS_DIR == Path("demo/snapshots")
    override = tmp_path / "private"
    assert snapshots_dir(tmp_path / "data", override) == override


def test_tracked_snapshots_validate_and_match_the_audit():
    directory = ROOT / DEFAULT_SNAPSHOTS_DIR
    assert directory.is_dir(), "fresh clones must ship demo/snapshots/"
    summaries = list_demo_snapshots(directory)
    assert {s.key for s in summaries} == TRACKED_SNAPSHOT_KEYS
    for summary in summaries:
        snapshot = load_demo_snapshot(directory, summary.key)
        assert snapshot is not None
        assert snapshot.key == summary.key
        assert snapshot.detail.report is not None
        if summary.key == "reference-morocco-ai":
            assert snapshot.detail.status == "complete"
            assert snapshot.detail.report.fallback is False
            assert snapshot.detail.report.generator == (
                "baseten:meta-models/muse-spark-open-1026"
            )
            assert snapshot.detail.report.acceptance == "ai-accepted"
            assert snapshot.detail.problems == []
        else:
            assert snapshot.detail.status == "partial"
            assert snapshot.detail.report.fallback is True
            assert snapshot.detail.report.generator == "deterministic-fallback"


def test_tracked_ai_snapshot_carries_trace_evidence():
    """The accepted run keeps its per-stage trace, usage, and repair verdict."""
    snapshot = load_demo_snapshot(ROOT / DEFAULT_SNAPSHOTS_DIR, "reference-morocco-ai")
    assert snapshot is not None
    detail = snapshot.detail
    assert detail.trace is not None
    assert detail.trace.usage == {
        "prompt_tokens": 61385,
        "completion_tokens": 23296,
        "llm_calls": 2,
    }
    assert {stage.name for stage in detail.trace.stages} == {
        "validate_inputs", "bundle", "retrieval", "ranking", "draft",
        "validate", "finalize",
    }
    assert detail.trace.validator_verdicts[0].startswith("[invalid-json]")
    assert detail.trace.validator_verdicts[-1] == "[repair-accepted]"
    assert detail.trace.draft_text == ""
    assert detail.trace.repair_text == ""
    assert detail.report is not None
    assert len(detail.report.statement_origins) == 14
    assert set(detail.report.statement_origins.values()) == {"model"}


def test_tracked_snapshots_carry_no_corpus_text():
    """Structural guard: evidence entries hold metadata fields only."""
    directory = ROOT / DEFAULT_SNAPSHOTS_DIR
    for summary in list_demo_snapshots(directory):
        snapshot = load_demo_snapshot(directory, summary.key)
        assert snapshot is not None
        dumped = snapshot.model_dump(mode="json")
        for item in dumped["detail"]["report"]["evidence"]:
            assert set(item) == EVIDENCE_METADATA_KEYS
            assert all(len(str(value)) < 600 for value in item.values())


def test_tracked_snapshots_pass_the_audit():
    """P25 guard: every tracked snapshot passes the pre-commit audit."""
    directory = ROOT / DEFAULT_SNAPSHOTS_DIR
    for summary in list_demo_snapshots(directory):
        snapshot = load_demo_snapshot(directory, summary.key)
        assert snapshot is not None
        assert audit_demo_snapshot(snapshot) == []


# --- Route handlers called directly (run everywhere) -------------------------


def test_routes_disabled_without_demo_mode(tmp_path):
    app = create_app()
    settings = Settings(data_dir=tmp_path, demo_mode=False)
    list_endpoint = endpoint_for(app, "/v1/demo/snapshots")
    get_endpoint = endpoint_for(app, "/v1/demo/snapshots/{key}")

    status, code = error_body(list_endpoint(settings))
    assert (status, code) == (404, "demo_mode_disabled")
    status, code = error_body(get_endpoint("demo-1", settings))
    assert (status, code) == (404, "demo_mode_disabled")


def test_routes_serve_snapshots_in_demo_mode(tmp_path, monkeypatch):
    write_sample(tmp_path, monkeypatch, key="demo-1")
    app = create_app()
    settings = Settings(data_dir=tmp_path, demo_mode=False).model_copy(
        update={"demo_mode": True, "demo_snapshots_dir": tmp_path / "snapshots"}
    )
    list_endpoint = endpoint_for(app, "/v1/demo/snapshots")
    get_endpoint = endpoint_for(app, "/v1/demo/snapshots/{key}")

    listed = list_endpoint(settings)
    assert isinstance(listed, DemoSnapshotList)
    assert listed.version == 1
    assert [s.key for s in listed.snapshots] == ["demo-1"]

    snapshot = get_endpoint("demo-1", settings)
    assert isinstance(snapshot, DemoSnapshotFile)
    assert snapshot.detail.scenario_id == "sc-demo-1"

    status, code = error_body(get_endpoint("ghost", settings))
    assert (status, code) == (404, "demo_snapshot_not_found")


# --- HTTP surface (needs sockets; runs outside restricted sandboxes) ---------


@pytest.fixture
def demo_client(tmp_path, monkeypatch):
    write_sample(tmp_path, monkeypatch, key="demo-1")
    settings = Settings(data_dir=tmp_path).model_copy(
        update={"demo_mode": True, "demo_snapshots_dir": tmp_path / "snapshots"}
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_http_list_and_get_snapshot(demo_client):
    listed = demo_client.get("/v1/demo/snapshots")
    assert listed.status_code == 200
    assert listed.json()["snapshots"][0]["key"] == "demo-1"

    fetched = demo_client.get("/v1/demo/snapshots/demo-1")
    assert fetched.status_code == 200
    assert fetched.json()["detail"]["scenario_id"] == "sc-demo-1"

    missing = demo_client.get("/v1/demo/snapshots/ghost")
    assert missing.status_code == 404
    assert missing.json()["detail"][0]["type"] == "demo_snapshot_not_found"


def test_http_demo_mode_off_is_404(tmp_path):
    settings = Settings(data_dir=tmp_path, demo_mode=False)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    response = client.get("/v1/demo/snapshots")
    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "demo_mode_disabled"
