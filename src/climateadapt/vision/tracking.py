"""MLflow run tracking behind a tiny adapter (``mlflow`` imported lazily).

:class:`RunTracker` talks to a real tracking store (file store by
default); :class:`FakeTracker` records the same calls in memory for
offline tests. No silent fallback: if ``mlflow`` is missing, the real
tracker raises with an install hint.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any


class FakeTracker:
    """In-memory stand-in recording params/metrics/artifacts."""

    def __init__(self) -> None:
        self.params: dict[str, str] = {}
        self.metrics: dict[str, float] = {}
        self.text_files: dict[str, dict] = {}
        self.artifacts: list[str] = []
        self.run_id = "fake-run-id"
        self.runs_started: list[str | None] = []

    @contextmanager
    def start_run(self, run_name: str | None = None):
        """Record the run name and yield ``self`` (mirrors RunTracker)."""
        self.runs_started.append(run_name)
        yield self

    def log_params(self, params: dict[str, Any]) -> None:
        """Record stringified params."""
        self.params.update({k: str(v) for k, v in params.items()})

    def log_metrics(self, metrics: dict[str, float]) -> None:
        """Record metrics."""
        self.metrics.update({k: float(v) for k, v in metrics.items()})

    def log_dict(self, payload: dict, name: str) -> None:
        """Record a JSON-serializable payload under ``name``."""
        self.text_files[name] = payload

    def log_artifact(self, path: str | Path) -> None:
        """Record an artifact path."""
        self.artifacts.append(str(path))


class RunTracker:
    """Thin MLflow tracker (SQLite store, e.g. ``sqlite:///data/mlruns/mlflow.db``).

    SQLite is used deliberately: since MLflow 3 the file store is in
    maintenance mode and refuses new stores without an opt-out flag.
    """

    def __init__(
        self,
        tracking_uri: str,
        experiment: str,
        artifact_location: str | None = None,
    ) -> None:
        try:
            import mlflow
        except ImportError as exc:
            raise ImportError(
                "mlflow is required for P16 run tracking "
                "(install the P16 vision tools; see docs/VISION_BASELINE.md)"
            ) from exc
        self._mlflow = mlflow
        mlflow.set_tracking_uri(tracking_uri)
        # MLflow 3 has no artifact_location on set_experiment: create the
        # experiment with our location when missing, then select it. The
        # location only applies at creation; re-runs reuse the stored one.
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=tracking_uri)
        if client.get_experiment_by_name(experiment) is None:
            client.create_experiment(experiment, artifact_location=artifact_location)
        mlflow.set_experiment(experiment)
        self.run_id: str | None = None

    @contextmanager
    def start_run(self, run_name: str | None = None):
        """Open an MLflow run, capturing its id, and yield ``self``."""
        with self._mlflow.start_run(run_name=run_name):
            run = self._mlflow.active_run()
            self.run_id = run.info.run_id if run is not None else None
            yield self

    def log_params(self, params: dict[str, Any]) -> None:
        """Log run parameters."""
        self._mlflow.log_params({k: str(v) for k, v in params.items()})

    def log_metrics(self, metrics: dict[str, float]) -> None:
        """Log run metrics."""
        self._mlflow.log_metrics({k: float(v) for k, v in metrics.items()})

    def log_dict(self, payload: dict, name: str) -> None:
        """Log a JSON artifact under ``name``."""
        self._mlflow.log_dict(payload, name)

    def log_artifact(self, path: str | Path) -> None:
        """Log a local file as an artifact."""
        self._mlflow.log_artifact(str(path))
