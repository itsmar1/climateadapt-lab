"""Train + evaluate P16 CropHarvest baselines with MLflow tracking.

Binary crop/non-crop on official v14 features: logistic regression and/or
random forest over aggregated per-band statistics, evaluated on the
official held-out ``test_features`` with per-class metrics, ROC-AUC and
bootstrap confidence intervals. Every run logs params/metrics/artifacts
to MLflow (SQLite store) and writes a JSON manifest.

Needs the vision tools (h5py, scikit-learn, mlflow) plus downloaded data
(see scripts/vision_download.py). Nothing here touches the network.

PowerShell::

    uv run python scripts/vision_baseline.py
    uv run python scripts/vision_baseline.py --models logreg --max-train-samples 5000
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from climateadapt.config import get_settings
from climateadapt.vision import features as vf
from climateadapt.vision import loader as vl
from climateadapt.vision import metrics as vm
from climateadapt.vision import splits as vs
from climateadapt.vision.constants import DEFAULT_SEED, ZENODO_FILES
from climateadapt.vision.models import build_model
from climateadapt.vision.report import assemble_manifest, write_manifest
from climateadapt.vision.tracking import RunTracker

# Test-grid stems whose positive class is generic crop (vs the maize/coffee
# crop-specific Kenya/Brazil grids). Used for the task-aligned sub-report.
CROP_GENERAL_FILES = frozenset({"china-crop", "togo-eval"})


def _file_inventory(data_dir: Path) -> dict:
    """Recorded (name -> size/md5-or-missing) for the three pinned files."""
    import hashlib

    inventory = {}
    for name, (size, md5) in ZENODO_FILES.items():
        path = data_dir / name
        if path.is_file() and path.stat().st_size == size:
            digest = hashlib.md5(path.read_bytes()).hexdigest()  # recorded check only
            inventory[name] = {"size": size, "md5": digest, "md5_match": digest == md5}
        else:
            have = path.stat().st_size if path.is_file() else 0
            inventory[name] = {"size": have, "md5": None, "md5_match": False}
    return inventory


def main(argv: list[str] | None = None) -> int:
    """Run the baseline protocol end to end; return a process exit code."""
    parser = argparse.ArgumentParser(description="Train + evaluate P16 baselines.")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--tracking-uri", default=None,
                        help="MLflow store (default: sqlite data/mlruns/mlflow.db).")
    parser.add_argument("--artifact-location", default=None,
                        help="MLflow artifact dir (default: data/mlruns/artifacts).")
    parser.add_argument("--experiment", default="p16-cropharvest-baseline")
    parser.add_argument("--models", nargs="+", choices=("logreg", "rf"), default=["logreg", "rf"])
    parser.add_argument("--feature-kind", choices=("mean_std", "flatten"), default="mean_std")
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--n-boot", type=int, default=1000)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    data_dir = Path(args.data_dir) if args.data_dir else settings.data_dir / "cropharvest"
    labels_path = data_dir / "labels.geojson"

    def _resolve(name: str) -> Path:
        for candidate in (data_dir / name / "arrays", data_dir / name):
            if candidate.is_dir():
                return candidate
        return data_dir / name

    features_dir = _resolve("features")
    test_features_dir = _resolve("test_features")
    for path in (labels_path, features_dir, test_features_dir):
        if not path.exists():
            print(f"missing input {path}; run scripts/vision_download.py first", file=sys.stderr)
            return 2
    store_dir = settings.data_dir / "mlruns"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = (store_dir / "mlflow.db").resolve().as_posix()
    tracking_uri = args.tracking_uri or f"sqlite:///{db_path}"
    artifact_location = args.artifact_location or str(store_dir / "artifacts")
    report_dir = Path(args.report_dir) if args.report_dir else data_dir / "reports"

    print(f"labels: {labels_path}")
    label_set = vl.read_labels(labels_path)
    rows = label_set.rows
    print(f"  {len(rows)} rows ({sum(r.is_test for r in rows)} flagged is_test, "
          f"{len(label_set.excluded)} excluded as invalid)")
    for excluded in label_set.excluded[:5]:
        print(f"    excluded row {excluded.number}: {excluded.reason}")
    train = vl.collect_train_paths(rows, features_dir)
    print(f"  train files: {len(train.entries)} (missing {train.missing}, "
          f"is_test-with-file excluded {train.test_flagged_with_files})")
    if not train.entries:
        print("no training feature files; aborting", file=sys.stderr)
        return 2

    keep = vs.capped_indices(len(train.entries), args.max_train_samples, args.seed)
    train_entries = [train.entries[i] for i in keep]
    print(f"  train subset: {len(train_entries)}/{len(train.entries)} (seed {args.seed})")

    def progress(done: int, total: int) -> None:
        if done % 5000 == 0 or done == total:
            print(f"  loaded {done}/{total}", flush=True)

    print("loading train matrices ...")
    X_train_raw, y_train = vl.load_matrices(train_entries, progress=progress)
    aggregate = vf.aggregate_mean_std if args.feature_kind == "mean_std" else vf.flatten
    train_agg = aggregate(X_train_raw)
    y_train = y_train[list(train_agg.kept)]
    print(f"  aggregated train ({args.feature_kind}): {train_agg.X.shape} "
          f"({len(train_agg.dropped)} non-finite rows excluded)")

    print("aggregating official test grids ...")
    grids = []
    for grid_path in sorted(test_features_dir.glob("*.h5")):
        grid = vl.aggregate_test_file(grid_path, kind=args.feature_kind)
        grids.append(grid)
        print(f"  {grid.name}: {grid.X.shape[0]} evaluable "
              f"({grid.n_ignored_missing} y=-1 ignored, {len(grid.dropped)} dropped)")
    if not grids:
        print(f"no test grids under {test_features_dir}; aborting", file=sys.stderr)
        return 2
    inventory = _file_inventory(data_dir)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for name in args.models:
        print(f"=== model: {name} ===")
        model = build_model(name, seed=args.seed)
        started = time.perf_counter()
        model.fit(train_agg.X, y_train)
        seconds = time.perf_counter() - started
        per_file = []
        for grid in grids:
            pred = [int(v) for v in model.predict(grid.X)]
            part_scores = ([float(v) for v in model.predict_proba(grid.X)[:, 1]]
                           if hasattr(model, "predict_proba") else None)
            rep = vm.evaluate(grid.y, pred, part_scores)
            per_file.append({"name": grid.name, "report": rep, "pred": pred,
                             "scores": part_scores})
            print(f"  {grid.name}: acc {rep.accuracy:.4f} macro-F1 {rep.macro_f1:.4f} "
                  f"(n={rep.n})")

        def _concat(idxs, _grids=grids, _per_file=per_file):
            """Pool true/pred/scores over grid positions (lists, no numpy)."""
            true_all, pred_all, scores_all, scored = [], [], [], True
            for i in idxs:
                true_all.extend(int(v) for v in _grids[i].y)
                pred_all.extend(_per_file[i]["pred"])
                if _per_file[i]["scores"] is None:
                    scored = False
                else:
                    scores_all.extend(_per_file[i]["scores"])
            return true_all, pred_all, (scores_all if scored else None)

        all_true, all_pred, all_scores = _concat(range(len(grids)))
        pooled = vm.evaluate(all_true, all_pred, all_scores)
        ci_acc = vm.bootstrap_ci(all_true, all_pred, "accuracy", args.n_boot, args.seed)
        ci_f1 = vm.bootstrap_ci(all_true, all_pred, "macro_f1", args.n_boot, args.seed)
        print(f"  pooled: acc {pooled.accuracy:.4f} "
              f"(95% CI {ci_acc[0]:.4f}-{ci_acc[1]:.4f}) "
              f"macro-F1 {pooled.macro_f1:.4f} "
              f"(95% CI {ci_f1[0]:.4f}-{ci_f1[1]:.4f}) ROC-AUC {pooled.roc_auc} "
              f"fit {seconds:.1f}s")
        for cls in pooled.classes:
            m = pooled.per_class[cls]
            print(f"  pooled class {cls}: P {m.precision:.4f} R {m.recall:.4f} "
                  f"F1 {m.f1:.4f} (n={m.support})")
        general_idx = [i for i, grid in enumerate(grids) if grid.name in CROP_GENERAL_FILES]
        general = None
        general_ci = None
        if general_idx:
            gen_true, gen_pred, gen_scores = _concat(general_idx)
            general = vm.evaluate(gen_true, gen_pred, gen_scores)
            gci_acc = vm.bootstrap_ci(gen_true, gen_pred, "accuracy", args.n_boot, args.seed)
            gci_f1 = vm.bootstrap_ci(gen_true, gen_pred, "macro_f1", args.n_boot, args.seed)
            general_ci = {"accuracy": {"lo": gci_acc[0], "hi": gci_acc[1]},
                          "macro_f1": {"lo": gci_f1[0], "hi": gci_f1[1]}}
            print(f"  crop-general (china-crop+togo-eval): acc {general.accuracy:.4f} "
                  f"(95% CI {gci_acc[0]:.4f}-{gci_acc[1]:.4f}) "
                  f"macro-F1 {general.macro_f1:.4f} (n={general.n})")

        tracker = RunTracker(tracking_uri, args.experiment,
                             artifact_location=artifact_location)
        manifest_path = report_dir / f"{stamp}_{name}_{args.feature_kind}.json"
        with tracker.start_run(run_name=f"{name}-{args.feature_kind}-{stamp}"):
            cls_name = type(model.named_steps["clf"]).__name__
            tracker.log_params({
                "model": name,
                "estimator": cls_name,
                "estimator_params": str(model.named_steps["clf"].get_params()),
                "feature_kind": args.feature_kind,
                "seed": args.seed,
                "n_train": len(y_train),
                "n_test_total": len(all_true),
                "n_test_files": len(grids),
                "test_files": ",".join(grid.name for grid in grids),
                "n_boot": args.n_boot,
                "dataset_version_id": 10251170,
                "labels_md5": str(inventory["labels.geojson"]["md5"]),
                "features_md5": str(inventory["features.tar.gz"]["md5"]),
                "test_features_md5": str(inventory["test_features.tar.gz"]["md5"]),
            })
            flat: dict[str, float] = {
                "accuracy": pooled.accuracy,
                "macro_f1": pooled.macro_f1,
                "accuracy_ci_lo": ci_acc[0],
                "accuracy_ci_hi": ci_acc[1],
                "macro_f1_ci_lo": ci_f1[0],
                "macro_f1_ci_hi": ci_f1[1],
                "fit_seconds": seconds,
            }
            if pooled.roc_auc is not None:
                flat["roc_auc"] = pooled.roc_auc
            for cls in pooled.classes:
                m = pooled.per_class[cls]
                flat[f"precision_{cls}"] = m.precision
                flat[f"recall_{cls}"] = m.recall
                flat[f"f1_{cls}"] = m.f1
            for entry in per_file:
                stem = entry["name"].replace("-", "_")
                flat[f"acc_{stem}"] = entry["report"].accuracy
            if general is not None:
                flat["crop_general_accuracy"] = general.accuracy
                flat["crop_general_macro_f1"] = general.macro_f1
            tracker.log_metrics(flat)
            manifest = assemble_manifest(
                model=name,
                seed=args.seed,
                feature_kind=args.feature_kind,
                n_train_rows=len(y_train),
                n_test_rows=len(all_true),
                train_capped=args.max_train_samples is not None
                and args.max_train_samples < len(train.entries),
                files=inventory,
                evaluation={
                    "overall": pooled.as_dict(),
                    "per_file": {entry["name"]: entry["report"].as_dict()
                                 for entry in per_file},
                    "crop_general": general.as_dict() if general is not None else None,
                },
                confidence_intervals={
                    "overall_accuracy": {"lo": ci_acc[0], "hi": ci_acc[1]},
                    "overall_macro_f1": {"lo": ci_f1[0], "hi": ci_f1[1]},
                    "crop_general": general_ci,
                },
                exclusions={
                    "invalid_label_rows": len(label_set.excluded),
                    "invalid_label_reasons": [e.reason for e in label_set.excluded[:5]],
                    "missing_train_files": train.missing,
                    "test_flagged_with_files": train.test_flagged_with_files,
                    "nonfinite_train_rows": len(train_agg.dropped),
                    "nonfinite_test_rows": sum(len(grid.dropped) for grid in grids),
                    "ignored_missing_test_labels": sum(grid.n_ignored_missing for grid in grids),
                },
                run_id=tracker.run_id,
                extra_params={"estimator": cls_name},
            )
            write_manifest(manifest_path, manifest)
            tracker.log_dict(manifest, "manifest.json")
            tracker.log_artifact(manifest_path)
            print(f"  mlflow run_id: {tracker.run_id}")
            print(f"  manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
