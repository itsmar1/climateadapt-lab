"""Evaluation metrics for binary crop/non-crop (numpy only).

Hand-rolled on purpose (same ethos as the hand-rolled BM25/RRF): small,
tested, and dependency-free. Zero-division yields 0.0 and is documented
in the report; confidence intervals use the percentile bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ClassMetrics:
    """Precision/recall/F1 for one class (0.0 when the denominator is 0)."""

    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class EvalReport:
    """Full binary-evaluation summary (JSON-serializable via ``as_dict``)."""

    accuracy: float
    n: int
    classes: tuple[int, ...]
    per_class: dict[int, ClassMetrics]
    macro_f1: float
    confusion: tuple[tuple[int, ...], ...]
    roc_auc: float | None

    def as_dict(self) -> dict:
        """Plain-JSON view (int keys stringified for readability)."""
        return {
            "accuracy": self.accuracy,
            "n": self.n,
            "classes": list(self.classes),
            "per_class": {
                str(cls): {
                    "precision": m.precision,
                    "recall": m.recall,
                    "f1": m.f1,
                    "support": m.support,
                }
                for cls, m in self.per_class.items()
            },
            "macro_f1": self.macro_f1,
            "confusion": [list(row) for row in self.confusion],
            "roc_auc": self.roc_auc,
        }


def _as_int_vector(values: np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(values).ravel()
    if array.size == 0:
        raise ValueError(f"{name} is empty")
    if not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"{name} must hold integer class labels")
    return array.astype(np.int64)


def rank_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """ROC-AUC by the Mann-Whitney rank statistic (binary, positive = 1)."""
    y_true = _as_int_vector(y_true, "y_true")
    scores = np.asarray(y_score, dtype=np.float64).ravel()
    if scores.shape != y_true.shape:
        raise ValueError("y_true and y_score must share a shape")
    if set(np.unique(y_true)) - {0, 1}:
        raise ValueError("rank_auc needs binary 0/1 labels")
    order = np.argsort(scores, kind="mergesort")
    ranked = np.empty_like(order, dtype=np.float64)
    ranked[order] = np.arange(1, len(scores) + 1, dtype=np.float64)
    # Average ranks within score ties.
    _, starts, counts = np.unique(scores[order], return_index=True, return_counts=True)
    for start, count in zip(starts, counts, strict=True):
        ranked[order[start : start + count]] = start + (count + 1) / 2.0
    n_pos = int((y_true == 1).sum())
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("rank_auc needs both classes present")
    return float((ranked[y_true == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def evaluate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray | None = None,
) -> EvalReport:
    """Accuracy, per-class P/R/F1, confusion matrix and optional ROC-AUC."""
    y_true = _as_int_vector(y_true, "y_true")
    y_pred = _as_int_vector(y_pred, "y_pred")
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must share a shape")
    classes = tuple(int(c) for c in np.unique(np.concatenate([y_true, y_pred])))
    pos = {cls: i for i, cls in enumerate(classes)}
    classes_arr = np.array(classes, dtype=np.int64)
    confusion = np.zeros((len(classes), len(classes)), dtype=np.int64)
    np.add.at(
        confusion,
        (np.searchsorted(classes_arr, y_true), np.searchsorted(classes_arr, y_pred)),
        1,
    )
    per_class: dict[int, ClassMetrics] = {}
    for cls in classes:
        i = pos[cls]
        tp = int(confusion[i, i])
        fp = int(confusion[:, i].sum() - tp)
        fn = int(confusion[i, :].sum() - tp)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[cls] = ClassMetrics(precision, recall, f1, int(confusion[i, :].sum()))
    macro_f1 = float(np.mean([m.f1 for m in per_class.values()]))
    roc_auc: float | None = None
    if y_score is not None and set(classes) <= {0, 1} and len(classes) == 2:
        roc_auc = rank_auc(y_true, y_score)
    return EvalReport(
        accuracy=float((y_true == y_pred).mean()),
        n=int(len(y_true)),
        classes=classes,
        per_class=per_class,
        macro_f1=macro_f1,
        confusion=tuple(tuple(int(v) for v in row) for row in confusion),
        roc_auc=roc_auc,
    )


def bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    statistic: str = "accuracy",
    n_boot: int = 1000,
    seed: int = 42,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Percentile bootstrap ``(lo, hi)`` for ``accuracy`` or ``macro_f1``."""
    if statistic not in ("accuracy", "macro_f1"):
        raise ValueError(f"unknown statistic {statistic!r}")
    if n_boot < 100:
        raise ValueError(f"n_boot must be >= 100, got {n_boot}")
    if not 0.0 < ci < 1.0:
        raise ValueError(f"ci must sit in (0, 1), got {ci}")
    y_true = _as_int_vector(y_true, "y_true")
    y_pred = _as_int_vector(y_pred, "y_pred")
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must share a shape")
    rng = np.random.RandomState(seed)
    draws = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        sample = rng.randint(0, len(y_true), size=len(y_true))
        report = evaluate(y_true[sample], y_pred[sample])
        draws[b] = report.accuracy if statistic == "accuracy" else report.macro_f1
    tail = (1.0 - ci) / 2.0
    return float(np.quantile(draws, tail)), float(np.quantile(draws, 1.0 - tail))
