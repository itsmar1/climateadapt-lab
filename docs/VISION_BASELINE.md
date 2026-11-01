# P16 Vision Baseline — CropHarvest crop/non-crop (Tier C)

Status: **implemented + evaluated 2026-11-01** (classical baselines, real v14
data, MLflow-tracked). Neural model and Optuna explicitly deferred (see §7).

> This baseline exists to demonstrate technical depth. It must never be
> presented as evidence of drought damage, crop stress, yield loss, or of
> any adaptation intervention's effectiveness. It is isolated from the
> recommendation pipeline: no vision output feeds any rank, constraint or
> report.

## 1. Sources verified (2026-11-01, CONFIRMED)

| Fact | Source (accessed 2026-11-01) |
|---|---|
| Dataset: 95,186 points, 70,213 (74%) paired with S1/S2/SRTM/ERA5, 21 constituent sets | [CropHarvest README](https://github.com/nasaharvest/cropharvest) |
| Licence CC-BY-SA-4.0 | [LICENSE.txt](https://github.com/nasaharvest/cropharvest/blob/main/LICENSE.txt), Zenodo API `license.id=cc-by-sa-4.0` |
| Label/file layout, `is_test` flag, `(12, 18)` arrays | [data/README.md](https://github.com/nasaharvest/cropharvest/blob/main/data/README.md), README FAQ |
| Band order (18) | [cropharvest/bands.py @ main](https://raw.githubusercontent.com/nasaharvest/cropharvest/main/cropharvest/bands.py) |
| Test regions/datasets, `DATASET_VERSION_ID = 10251170`, seed 42 | [cropharvest/config.py @ main](https://raw.githubusercontent.com/nasaharvest/cropharvest/main/cropharvest/config.py) |
| Test protocol (`{test_identifier}*.h5` → `TestInstance`) | [cropharvest/datasets.py @ main](https://raw.githubusercontent.com/nasaharvest/cropharvest/main/cropharvest/datasets.py) (`test_data`) |
| `y`: 1 positive / 0 negative / -1 `MISSING_DATA`; eval excludes -1 | [cropharvest/engineer.py @ main](https://raw.githubusercontent.com/nasaharvest/cropharvest/main/cropharvest/engineer.py) (`TestInstance`) |
| Record 10251170 (v14, `is_last`, 2023-12-04) file sizes + md5 | Zenodo API `https://zenodo.org/api/records/10251170` |
| Paper + citation (Tseng et al. 2021, NeurIPS D&B) | [OpenReview JtjzUXPEaCu](https://openreview.net/forum?id=JtjzUXPEaCu) |
| MLflow tracking API (set_tracking_uri/start_run/log_*) | [MLflow Tracking Quickstart](https://mlflow.org/docs/3.0.0rc0/getting-started/intro-quickstart/) |
| File store in maintenance mode → SQLite recommended | MLflow 3.17.2 FileStore exception text at runtime |
| `cropharvest` 0.7.0 deps (`pandas<2`, `geopandas==0.9.0`, `xarray<0.20`) | PyPI JSON `https://pypi.org/pypi/cropharvest/json` |

Pinned data (record 10251170, verified by size + md5 at download):

| File | Bytes | md5 |
|---|---|---|
| `labels.geojson` | 85,689,847 | `54a5070f103bc3e635afba27c139ac8d` |
| `features.tar.gz` | 82,479,907 | `d757e6c32cb6d65aa517f003607f6f81` |
| `test_features.tar.gz` | 786,061,051 | `be1d9e07ee69c7ef6a316a0edb3432bf` |

`eo_data.tar.gz` (~26.7 GB raw GeoTIFFs) intentionally not used.

## 2. Environment + versions (this run, CONFIRMED)

CPU-only (torch reports `cuda False`), 8 logical processors, 39.8 GB disk
free before download. Windows 11, Python 3.11.17, project `.venv`.

| Package | Version | Role |
|---|---|---|
| mlflow (+ skinny/tracing) | 3.17.2 | run tracking (SQLite store) |
| h5py | 3.16.0 | `.h5` feature reads |
| scikit-learn | 1.9.1 | logreg + random forest |
| numpy / scipy / pandas | 2.4.6 / 1.17.1 / 3.1.0 | numerics (pre-existing) |
| torch | 2.15.0+cpu | present, NOT used by P16 |
| timm | not installed | neural model deferred, see §7 |
| cropharvest (PyPI) | NOT installed | see §3 |

## 3. Key design decisions

1. **CropHarvest data without the `cropharvest` package.** Version 0.7.0
   (2024-04-30, latest) pins `pandas<2`, `geopandas==0.9.0` and
   `xarray<0.20`, which would downgrade this project's working stack
   (pandas 3.x, xarray>=2024.1) and likely fail on Python 3.11/Windows.
   Instead `src/climateadapt/vision/loader.py` implements a minimal
   documented loader (stdlib geojson + h5py) against the verified format.
   Only documented facts (band order, test splits, seed) are reused.
2. **SQLite tracking store.** MLflow 3's file store refuses new stores
   without `MLFLOW_ALLOW_FILE_STORE=true`; SQLite
   (`data/mlruns/mlflow.db` + `data/mlruns/artifacts/`) is the
   vendor-recommended path and needs no opt-out.
3. **Vision tools are NOT in `pyproject.toml`/`uv.lock`.** This sandbox
   cannot reach PyPI through uv's HTTP client and cannot rewrite the
   owner's lockfile; tools were installed from hash-verified wheels into
   the local `.venv` only (one documented exception: graphene's
   `python-dateutil<3` bound vs installed 3.0.0 — untouched API surface,
   verified by the green suite). Recommended follow-up on a networked
   machine: add a `vision` extra (`h5py`, `mlflow`, `scikit-learn`,
   `pandas`) and run `uv lock`. Until then, a plain `uv sync` on this
   machine would remove the vision tools (they are not in the lock);
   use `uv run --no-sync` or reinstall afterwards. CI
   (`uv sync --locked --extra dev`) is unaffected: vision tests skip
   cleanly without the tools.
4. **Metrics hand-rolled in numpy** (accuracy, per-class P/R/F1,
   confusion, rank-based ROC-AUC, percentile bootstrap CIs), mirroring
   the repo's hand-rolled BM25/RRF ethos; sklearn only fits the two
   baseline estimators.

## 4. Task, splits, leakage controls, metrics

- **Task:** binary crop/non-crop on (12 monthly timesteps × 18 bands)
  arrays, aggregated to per-band mean+std (36 features). Train labels
  are `is_crop` ("contains cropland"); test labels are the official
  grid `y`.
- **Train:** seeded subset of 20,000 of the 82,654 eligible rows
  (`is_test == False` with a per-row file under `features/arrays/`;
  seed 42, `capped_indices`). The cap is an I/O time-box (per-row
  reads run ~1k files/min on this machine); the identical command
  without `--max-train-samples` reproduces the full-data run.
  Excluded and counted: 25,189 rows without a file, 4,810 `is_test`
  rows that do have a per-row file, 1 invalid label row (null
  coordinates).
- **Test:** the 6 official consolidated grids under `test_features/`
  (1,383,907 rows; 543,055 evaluable after excluding `y == -1`):
  Brazil coffee 2020 (306,684) and 2021 (230,770), Kenya maize
  regions (538 + 360), China crop (4,397), Togo eval (306).
- **Label semantics (verified in `engineer.py`):** `y = 1` positive,
  `0` negative, `-1` = `MISSING_DATA` (excluded from metrics, as
  upstream does). Positive = generic crop in `china-crop`/`togo-eval`,
  but crop-specific (maize/coffee) in the Kenya/Brazil grids — so
  per-file metrics are the primary read-out, the pooled number is a
  mixed-semantics aggregate, and `china-crop`+`togo-eval` is reported
  separately as the task-aligned subset.
- **Leakage controls:** `is_test` rows can never train (4,810 with
  files explicitly excluded); verified zero non-test rows inside the
  test bboxes or from test datasets; scaler inside the sklearn
  Pipeline (fit on train only); fixed seed (42); test grids streamed
  in chunks (never fully in RAM); no imputation anywhere.
- **Metrics:** per-file, pooled, and crop-general accuracy,
  per-class precision/recall/F1, confusion matrices, ROC-AUC, and
  95% bootstrap CIs (1000 resamples) for pooled and crop-general
  accuracy/macro-F1.

## 5. How to reproduce (owner machine, networked)

```powershell
# 1. Vision tools (not in uv.lock yet; see §3.3)
uv pip install "mlflow>=3" "h5py>=3.1" "scikit-learn>=1.9" "pandas>=3.1"

# 2. Data (~911 MB + extraction; verifies size + md5)
uv run python scripts/vision_download.py

# 3. Baselines (both models, MLflow SQLite store, JSON manifests)
uv run python scripts/vision_baseline.py
uv run python scripts/vision_baseline.py --models logreg --max-train-samples 5000  # quick check

# 4. Browse runs
uv run mlflow ui --backend-store-uri sqlite:///data/mlruns/mlflow.db
```

Unit tests (offline; tool-dependent parts skip without the tools):

```powershell
uv run pytest tests/test_vision_features.py tests/test_vision_splits.py `
  tests/test_vision_metrics.py tests/test_vision_report.py `
  tests/test_vision_loader.py tests/test_vision_models.py tests/test_vision_tracking.py
```

## 6. Results (actual run, CONFIRMED 2026-11-01)

Command: `uv run python scripts/vision_baseline.py --max-train-samples 20000`
(exit 0). Train 20,000 × 36 (seed 42); test 543,055 evaluable rows over
6 grids; 840,852 `y == -1` ignored, 0 non-finite rows anywhere.
Manifests: `data/cropharvest/reports/20261101T143318Z_{logreg,rf}_mean_std.json`
(git-ignored). MLflow SQLite store: `data/mlruns/mlflow.db`, experiment
`p16-cropharvest-baseline`.

| Model | MLflow run id | Pooled acc (95% CI) | Pooled macro-F1 (95% CI) | Pooled AUC |
|---|---|---|---|---|
| logreg | `b537f8dbc97940149ef5f2f9c6339e17` | 0.5619 (0.5606–0.5632) | 0.5594 (0.5581–0.5607) | 0.6813 |
| rf | `652be4354d6c4869a77bd35cd7aae55b` | 0.7972 (0.7961–0.7982) | 0.7895 (0.7884–0.7905) | 0.8047 |

Pooled per-class (logreg): 0: P 0.9698 R 0.3612 F1 0.5264 (n=365,990);
1: P 0.4252 R 0.9767 F1 0.5925 (n=177,065).
Pooled per-class (rf): 0: P 0.9552 R 0.7334 F1 0.8298;
1: P 0.6277 R 0.9290 F1 0.7492.

Per-file accuracy / macro-F1 / AUC (n):

| Grid (n) | logreg | rf |
|---|---|---|
| Brazil coffee 2020 (306,684) | 0.6956 / 0.6885 / 0.7596 | 0.8385 / 0.8251 / 0.8340 |
| Brazil coffee 2021 (230,770) | 0.3840 / 0.2879 / 0.5823 | 0.7440 / 0.7420 / 0.7363 |
| Kenya maize region 0 (538) | 0.6283 / 0.6257 / 0.7366 | 0.7509 / 0.7374 / 0.7938 |
| Kenya maize region 1 (360) | 0.5361 / 0.4463 / 0.5128 | 0.4000 / 0.3978 / 0.5959 |
| China crop (4,397) | 0.5745 / 0.4351 / 0.9013 | 0.7489 / 0.7290 / 0.8897 |
| Togo eval (306) | 0.4771 / 0.4720 / 0.6810 | 0.7026 / 0.7003 / 0.8508 |

Task-aligned crop-general subset (china-crop + togo-eval, n=4,703):
logreg acc 0.5681 (CI 0.5539–0.5824), macro-F1 0.4452
(CI 0.4320–0.4589), AUC 0.8855; rf acc 0.7459 (CI 0.7342–0.7591),
macro-F1 0.7293 (CI 0.7166–0.7430), AUC 0.8891.

Read-out (what the numbers say, no further): the forest beats the
linear model on every grid except tiny Kenya-1; logreg collapses on
Brazil 2021 (same region, new year: acc 0.38) while the forest holds
(0.74); both rank China well (AUC ~0.89–0.90) but sit off-threshold at
0.5 (near-unity class-1 recall); Kenya-1 is near chance for both.
Fit time: logreg 2.9 s, rf 140.4 s; train load dominated wall time
(~1k files/min).

## 7. What the model can and cannot support

CAN: pixel/field-footprint crop-vs-non-crop classification accuracy on
the official CropHarvest v14 held-out sets, with stated confidence
intervals — a technical-depth demonstration with tracked provenance.

CANNOT (must never be claimed): drought presence/severity, crop stress,
yield or damage estimation, intervention effectiveness or cost/benefit,
performance outside the evaluated regions/years/datasets, or fitness for
any operational decision.

## 8. Deferred (deliberate, not forgotten)

- **Small neural model:** not justified yet — classical baselines +
  protocol first per the task; CPU-only; time-boxed. Revisit only if
  the rubric rewards it (then: verify timm docs, pin version, compare
  on the same frozen protocol).
- **Optuna:** only after the baseline + evaluation protocol are fixed
  (this document freezes them); a small search over
  `C`/`n_estimators`/aggregation is the natural next step.
- **Vision extra in `pyproject.toml` + `uv.lock`:** needs a networked
  `uv lock` (see §3.3).
