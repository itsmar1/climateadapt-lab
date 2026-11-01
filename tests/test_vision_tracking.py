"""Tests for vision.tracking (real mlflow part skips when missing)."""

from __future__ import annotations

import re
import sys

import pytest

from climateadapt.vision.tracking import FakeTracker, RunTracker


def test_fake_tracker_records_everything():
    """The fake mirrors the real API and records calls for assertions."""
    tracker = FakeTracker()
    with tracker.start_run(run_name="demo") as active:
        assert active is tracker
        tracker.log_params({"seed": 42, "model": "rf"})
        tracker.log_metrics({"accuracy": 0.9})
        tracker.log_dict({"a": 1}, "manifest.json")
        tracker.log_artifact("some/path.json")
    assert tracker.run_id == "fake-run-id"
    assert tracker.runs_started == ["demo"]
    assert tracker.params == {"seed": "42", "model": "rf"}
    assert tracker.metrics == {"accuracy": 0.9}
    assert tracker.text_files == {"manifest.json": {"a": 1}}
    assert tracker.artifacts == ["some/path.json"]


def test_missing_mlflow_raises_install_hint(monkeypatch):
    """Without mlflow the real tracker raises an install hint."""
    monkeypatch.setitem(sys.modules, "mlflow", None)
    with pytest.raises(ImportError, match="mlflow"):
        RunTracker("file:///tmp/nope", "exp")


def test_run_tracker_roundtrip_on_sqlite_store(tmp_path):
    """A real SQLite-store run logs params/metrics/artifacts, read back by id."""
    mlflow = pytest.importorskip("mlflow")
    store = tmp_path / "mlruns"
    uri = f"sqlite:///{store / 'mlflow.db'}"
    tracker = RunTracker(uri, "test-exp", artifact_location=str(store / "artifacts"))
    artifact = tmp_path / "note.txt"
    artifact.write_text("hello")
    with tracker.start_run(run_name="smoke"):
        tracker.log_params({"seed": 7})
        tracker.log_metrics({"accuracy": 0.75})
        tracker.log_dict({"n": 3}, "manifest.json")
        tracker.log_artifact(artifact)
    assert tracker.run_id is not None
    assert re.fullmatch(r"[0-9a-f]{32}", tracker.run_id)
    client = mlflow.tracking.MlflowClient(tracking_uri=uri)
    run = client.get_run(tracker.run_id)
    assert run.data.params["seed"] == "7"
    assert run.data.metrics["accuracy"] == pytest.approx(0.75)
    assert (store / "mlflow.db").exists()
    assert list((store / "artifacts").rglob("note.txt")) != []
