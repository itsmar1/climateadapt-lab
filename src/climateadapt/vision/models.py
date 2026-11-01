"""Classical baseline models (``scikit-learn``, imported lazily).

Two baselines, both on aggregated per-band statistics (see
:mod:`features`): L2 logistic regression and a random forest. Pipelines
carry their own preprocessing so nothing is ever fit on test data.
"""

from __future__ import annotations

from typing import Any

LOGREG_DEFAULTS: dict[str, Any] = {"max_iter": 2000, "C": 1.0}
RF_DEFAULTS: dict[str, Any] = {"n_estimators": 100}


def _sklearn():
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise ImportError(
            "scikit-learn is required for P16 training "
            "(install the P16 vision tools; see docs/VISION_BASELINE.md)"
        ) from exc
    return LogisticRegression, Pipeline, StandardScaler


def build_logreg(seed: int = 42, max_iter: int = 2000, c: float = 1.0):
    """Logistic regression on standardized aggregated features."""
    LogisticRegression, Pipeline, StandardScaler = _sklearn()
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(max_iter=max_iter, C=c, random_state=seed),
            ),
        ]
    )


def build_random_forest(seed: int = 42, n_estimators: int = 100):
    """Random forest on raw aggregated features (trees need no scaling)."""
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.pipeline import Pipeline
    except ImportError as exc:
        raise ImportError(
            "scikit-learn is required for P16 training "
            "(install the P16 vision tools; see docs/VISION_BASELINE.md)"
        ) from exc
    return Pipeline(
        [("clf", RandomForestClassifier(n_estimators=n_estimators, random_state=seed))]
    )


def build_model(name: str, seed: int = 42):
    """Build a baseline by name (``logreg`` or ``rf``)."""
    if name == "logreg":
        return build_logreg(seed=seed)
    if name == "rf":
        return build_random_forest(seed=seed)
    raise ValueError(f"unknown model {name!r} (want 'logreg' or 'rf')")
