"""Tests for vision.metrics (numpy only; always run, no network)."""

from __future__ import annotations

import numpy as np
import pytest

from climateadapt.vision.metrics import bootstrap_ci, evaluate, rank_auc


def test_perfect_prediction_scores_one():
    """A perfect binary prediction scores 1.0 everywhere incl. AUC."""
    report = evaluate(
        np.array([0, 0, 1, 1]),
        np.array([0, 0, 1, 1]),
        np.array([0.1, 0.2, 0.8, 0.9]),
    )
    assert report.accuracy == pytest.approx(1.0)
    assert report.macro_f1 == pytest.approx(1.0)
    assert report.roc_auc == pytest.approx(1.0)
    assert report.confusion == ((2, 0), (0, 2))
    assert report.per_class[0].support == 2
    assert report.per_class[1].support == 2


def test_hand_checked_confusion_and_macro_f1():
    """4/6 right with symmetric errors -> accuracy 2/3, macro-F1 2/3."""
    report = evaluate(np.array([0, 0, 0, 1, 1, 1]), np.array([0, 0, 1, 1, 1, 0]))
    assert report.accuracy == pytest.approx(2 / 3)
    assert report.confusion == ((2, 1), (1, 2))
    for cls in (0, 1):
        metrics = report.per_class[cls]
        assert metrics.precision == pytest.approx(2 / 3)
        assert metrics.recall == pytest.approx(2 / 3)
        assert metrics.f1 == pytest.approx(2 / 3)
    assert report.macro_f1 == pytest.approx(2 / 3)
    assert report.roc_auc is None


def test_missing_predicted_class_gives_zeros_not_crash():
    """Zero-division classes score 0.0 (documented) instead of raising."""
    report = evaluate(np.array([0, 1]), np.array([0, 0]))
    assert report.accuracy == pytest.approx(0.5)
    assert report.per_class[1].precision == 0.0
    assert report.per_class[1].recall == 0.0
    assert report.per_class[1].f1 == 0.0
    assert report.per_class[1].support == 1


def test_rank_auc_hand_checked_and_ties():
    """3 of 4 positive/negative pairs ordered -> AUC 0.75; full tie -> 0.5."""
    assert rank_auc(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.35, 0.8])) == pytest.approx(
        0.75
    )
    assert rank_auc(np.array([0, 1]), np.array([0.5, 0.5])) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="both classes"):
        rank_auc(np.array([1, 1]), np.array([0.2, 0.9]))
    with pytest.raises(ValueError, match="share a shape"):
        rank_auc(np.array([0, 1]), np.array([0.2]))


def test_evaluate_rejects_bad_inputs():
    """Empty, non-integer and mismatched inputs fail loudly."""
    with pytest.raises(ValueError, match="empty"):
        evaluate(np.array([]), np.array([]))
    with pytest.raises(ValueError, match="integer"):
        evaluate(np.array([0.5, 1.5]), np.array([0, 1]))
    with pytest.raises(ValueError, match="share a shape"):
        evaluate(np.array([0, 1]), np.array([0]))


def test_bootstrap_ci_deterministic_and_bracketing():
    """Same seed repeats exactly; the interval brackets the point estimate."""
    rng = np.random.RandomState(0)
    y_true = rng.randint(0, 2, size=200)
    y_pred = np.where(rng.rand(200) < 0.8, y_true, 1 - y_true)
    point = evaluate(y_true, y_pred).accuracy
    first = bootstrap_ci(y_true, y_pred, "accuracy", n_boot=200, seed=42)
    second = bootstrap_ci(y_true, y_pred, "accuracy", n_boot=200, seed=42)
    assert first == second
    assert first[0] <= point <= first[1]
    assert first[0] < first[1]
    lo, hi = bootstrap_ci(y_true, y_pred, "macro_f1", n_boot=200, seed=42)
    assert lo <= evaluate(y_true, y_pred).macro_f1 <= hi
    with pytest.raises(ValueError, match="unknown statistic"):
        bootstrap_ci(y_true, y_pred, "roc_auc", n_boot=100, seed=1)
    with pytest.raises(ValueError, match="n_boot"):
        bootstrap_ci(y_true, y_pred, "accuracy", n_boot=50, seed=1)
