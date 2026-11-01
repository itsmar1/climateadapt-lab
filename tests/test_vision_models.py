"""Tests for vision.models (sklearn parts skip when missing)."""

from __future__ import annotations

import sys

import numpy as np
import pytest

from climateadapt.vision.models import build_logreg, build_model, build_random_forest


def test_unknown_model_fails_without_sklearn():
    """Unknown names fail before any optional import happens."""
    with pytest.raises(ValueError, match="unknown model"):
        build_model("resnet")


def test_missing_sklearn_raises_install_hint(monkeypatch):
    """Without scikit-learn the builders raise an install hint."""
    monkeypatch.setitem(sys.modules, "sklearn", None)
    monkeypatch.setitem(sys.modules, "sklearn.linear_model", None)
    monkeypatch.setitem(sys.modules, "sklearn.ensemble", None)
    monkeypatch.setitem(sys.modules, "sklearn.pipeline", None)
    monkeypatch.setitem(sys.modules, "sklearn.preprocessing", None)
    with pytest.raises(ImportError, match="scikit-learn"):
        build_logreg()
    with pytest.raises(ImportError, match="scikit-learn"):
        build_random_forest()


def test_pipelines_carry_shapes_and_determinism():
    """Logreg scales, RF does not, and fixed seeds repeat predictions."""
    pytest.importorskip("sklearn")
    logreg = build_model("logreg", seed=7)
    assert list(logreg.named_steps) == ["scaler", "clf"]
    forest = build_model("rf", seed=7)
    assert list(forest.named_steps) == ["clf"]
    rng = np.random.RandomState(0)
    X = rng.normal(size=(40, 36))
    y = (X[:, 0] > 0).astype(int)
    for name in ("logreg", "rf"):
        first = build_model(name, seed=7).fit(X, y).predict(X)
        second = build_model(name, seed=7).fit(X, y).predict(X)
        assert (first == second).all()
    assert build_model("logreg").named_steps["clf"].max_iter == 2000
    assert build_model("rf").named_steps["clf"].n_estimators == 100
