# Implementation Status

Handoff date: 2026-10-28.

P00 audit update: 2026-10-30 (see `docs/handoff/AUDIT_REPORT.md`). The audit verified the
repository against this document on branch `feat/muse-code-handoff` @ `12f3ac6`. Where §1b
below gives a verified result, it supersedes the pre-audit snapshot in §1.

## 0. Evidence basis — read this first

The author (Claude, browser chat) **could not inspect the repository**. The only project file directly visible was `technical_blueprint.txt`. Everything below comes from two sources:

1. **Source code written by Claude in the conversation**, which the owner reports saving locally. The owner also edited some files (fixed ruff findings across batches, changed one test regex in `tests/test_chirps.py`, applied several "insert/replace" patches). **The local files may differ from the conversation text.**
2. **Terminal logs pasted by the owner** (pytest, ruff, scripts, API calls).

Therefore file paths below are *expected* paths based on delivered code. The first Muse Code task (P00) must confirm each against the real tree (`git ls-files`). The repository is authoritative.

Evidence legend used in tables:

- **T** = covered by tests that passed in the last full pasted run (see §1).
- **R** = exercised on real data/services in the owner's pasted logs.
- **U** = written but not exercised, or no log shows it.
- **—** = not applicable.

## 1. Verification snapshot

| Item | Result | Source |
|---|---|---|
| Last pasted full `uv run pytest` | **536 collected, 534 passed, 2 failed**, 7 min 44 s | owner log |
| Failures | `tests/test_rag_text_chunking.py::test_tampering_and_wrong_pages_fail_verification` and `::test_number_heavy_windows_are_dropped_and_counted` | owner log |
| Diagnosis | Both are **test bugs**: first test inserted a word before the chunk instead of editing a word inside it; second miscounted its own data (125 prose words, not 100). Source code behaved correctly. | Claude hand-trace; UNVERIFIED by execution |
| Last pasted `uv run ruff check .` | **2 errors, B008** (`ChunkingParams()` in default arguments): `src/climateadapt/rag/chunking.py` (~line 61) and `src/climateadapt/rag/ingest.py` (~line 108) | owner log |
| Proposed fixes (4) | Add `DEFAULT_CHUNKING_PARAMS = ChunkingParams()` constant and use it in both signatures/imports; edit two tests (use `pages[0].text.replace("w0030","w9999")`; change `* 25` to `* 20`) | Claude message; **not confirmed applied or passing** |
| Earlier green runs | 437 passed + ruff clean (after temperature batch). KS-statistic test failure was later fixed; `test_spi_diagnostics.py` shows 8/8 passing in the 536 run | owner logs |
| Warning in every run | `StarletteDeprecationWarning`: `httpx` with `starlette.testclient` deprecated (message suggests `httpx2`) | owner log; cause not investigated |
| Frontend tests, CI | none exist | — |

Test counts per module in the 536 run (from the owner's log): analysis_and_schemas 15, api 19, api_chirps 16, api_spi 18, cds_client 8, chirps 29, chirps_boundary 6, chirps_remote 16, era5_land 37, era5_land_fallback 19, era5_soil_moisture 18, geo 6, periods_and_coverage 46, rag_bm25_fusion 15, rag_citations 11, rag_end_to_end 5, rag_ingest_fetch 12, rag_manifest 17, rag_text_chunking 13 (2 failed), rainfall 27, rainfall_pipeline 25, spi 54, spi_diagnostics 8, spi_era5_pipeline 16, spi_pipeline 16, temperature 23, temperature_pipeline 14, units 27.

## 1b. P00 audit verification (CONFIRMED 2026-10-30)

Source: `docs/handoff/AUDIT_REPORT.md` §4–§5 (offline, read-only; branch
`feat/muse-code-handoff` @ `12f3ac6`). No new source-code defects were identified.

| Item | Result |
|---|---|
| Full suite (`python -m pytest -q --tb=short`; canonical re-run: `uv run pytest`) | **536 passed, 1 warning in 576.54s (0:09:36)**, exit 0. The 1 warning is the known `StarletteDeprecationWarning` (KI-04). No skips, no failures. |
| `ruff check .` | **All checks passed!** (exit 0). Both B008 findings are gone. |
| KI-01 four fixes | **Already present and verified working** (AUDIT_REPORT §7): `DEFAULT_CHUNKING_PARAMS` in `rag/chunking.py:37,64` and `rag/ingest.py:19,108`; tamper test edits a word inside the chunk (`tests/test_rag_text_chunking.py:62`); number-heavy test uses `* 20` (`tests/test_rag_text_chunking.py:82`). Green suite proves they work. |
| Per-module test breakdown | Total 536 CONFIRMED (identical collection count, now 536 passed vs 534+2). Per-module numbers above were **not** individually re-verified — treat them as REPORTED-compatible. |
| File inventory vs §2 | CONFIRMED accurate: all 41 `src`, 31 `tests`, 13 `scripts`, corpus and doc paths present, no renames. Two corrections: tracked `uv.lock` exists but was unmentioned in the handoff (observation, not a problem); `scripts/chirps_layout_probe.py` is **confirmed deleted**. |
| API routes | 4 app routes + 4 FastAPI docs routes, verified by import (see §2.5). |

### Milestone status (verified 2026-10-30; CONFIRMED)

No milestone definitions exist in the repo (`technical_blueprint.txt` was never committed),
so this mapping follows the handoff's implied milestones. "Complete" = implemented + tested.

| Milestone | Status | Evidence |
|---|---|---|
| M0 (project setup/config) | **Complete** | `pyproject.toml` + `uv.lock`, `.env.example`, `config.py` (`CLIMATEADAPT_` prefix), tests layout, ruff/pytest config; exercised by the green suite. |
| M1 (CHIRPS connector + precipitation indicators + API) | **Complete** | `data/chirps.py`, `data/chirps_remote.py`, `indicators/rainfall.py`, `indicators/spi.py`, `pipelines/rainfall_anomaly.py`, `pipelines/spi.py`, 3 CHIRPS API routes + `/health`. Real-data behavior is REPORTED (past logs; local cache files corroborate runs happened), not re-executed in the audit. |
| M2 (ERA5-Land connector + temperature/SPI indicators) | **Complete as CLI** | `data/era5_land.py`, `data/cds_client.py`, `indicators/temperature.py`, `indicators/spi_diagnostics.py`, `indicators/units.py`, `pipelines/spi_era5.py`, `pipelines/temperature_anomaly.py`, CLI scripts. ERA5 API exposure does not exist (expected — P05 scope). |
| M3 (computer vision) | **Not started** | No CV code, deps, or docs beyond handoff mentions; deferral decision still pending with the owner. |
| M4 (scientific RAG, first batch) | **Partially complete** | Implemented + tested: manifest, fetch, ingest, page-aware chunking + provenance verification, BM25, RRF, `Bm25Retriever`/`HybridRetriever`, citations, evaluation harness. Missing within M4: dense E5 + Qdrant retriever (no code at all), RAG API routes, 4 of 8 corpus documents, page-level gold annotations, printed page labels. `HybridRetriever` is generic/inert without a second retriever. |

M5 (recommendations) / M6 (agent + LLM), frontend, persistence, and Docker/CI are all
**not started** — no code, not partial (AUDIT_REPORT §6).

### Environment note (verified 2026-10-30; CONFIRMED)

Node.js v16.13.1 / npm 8.1.2 is installed — Node 16 is end-of-life and **below the Node 18+
that current Vite requires**. A Node upgrade is a prerequisite before any frontend work
(P12). Verified environment otherwise: Python 3.11.17 (uv-managed), pytest 9.1.1,
ruff 0.17.2, uv 0.13.5, Docker engine 29.8.2 present (no Docker files exist yet).

## 2. Completed components (expected paths)

### 2.1 Project configuration
| Path | Contents | Evidence |
|---|---|---|
| `pyproject.toml` | setuptools src layout; deps: cdsapi, fastapi, httpx, netcdf4, numpy, pydantic, pydantic-settings, pypdf, rasterio, scipy, uvicorn, xarray; dev: pytest, ruff; pytest `filterwarnings` for rasterio; ruff `E,F,I,B,UP`, line 100 | R (`uv sync` works) |
| `uv.lock` | Tracked lockfile (P00 audit 2026-10-30: present but unmentioned in the handoff; installed venv matches it) | CONFIRMED present |
| `.env.example`, `.gitignore` | env template (data dir, downloads flag, CHIRPS mode, prefetch workers, CDS retry bounds); `.gitignore` includes `data/corpus/`, `data/cache/`, `.env` | U (content), R (used) |
| `README.md` | Setup, API, scripts, CDS credentials, error codes. **Was stale:** no RAG commands, no soil-moisture note (both added 2026-10-30); CDS retry bounds detail still missing | partially stale |
| `src/climateadapt/__init__.py`, `config.py` | `Settings` (env prefix `CLIMATEADAPT_`): environment, log_level, data_dir, allow_downloads, http_timeout_seconds, http_user_agent, chirps_base_url, chirps_access (`remote`/`download`), prefetch_workers, cds_retry_max, cds_sleep_max_seconds, cds_timeout_seconds, baseten_base_url, baseten_model_id, baseten_api_key (SecretStr; P03 2026-10-30) | T, R |

### 2.2 Data connectors (`src/climateadapt/data/`)
| Path | Purpose | Evidence |
|---|---|---|
| `errors.py` | Exception hierarchy (`OutsideCoverageError`, `DataNotAvailableError`, `DownloadError`, `DataIntegrityError`, `MissingDataError`) | T |
| `periods.py` | `YearMonth`, `iter_months` | T |
| `coverage.py` | `BoundingBox` (half-open), CHIRPS (60°S–60°N, from 1981-01) and ERA5-Land (global, from 1950-01) coverage constants, coordinate/month validation | T |
| `provenance.py` | `Provenance` model (download vs remote-range-read modes) | T, R |
| `chirps.py` | Download store, sampling (`sample_dataset`), boundary flag, `ChirpsV3Client`, `PointSeries`, `build_chirps_client` | T, R |
| `chirps_remote.py` | `ChirpsRemoteStore`: single-pixel HTTP range reads via GDAL `/vsicurl/`, per-point JSON cache, parallel prefetch | T, R |
| `cds_client.py` | Builds a `cdsapi.Client` passing only retry/timeout options the installed signature exposes | T; signature half CONFIRMED for cdsapi 0.7.7 (P02 2026-10-30: all three options exist and are passed); **live retry behavior still U** |
| `era5_land.py` | `VARIABLES` (2m_temperature, total_precipitation, volumetric_soil_water_layer_1/2/3), CDS download adapter, per-month cache with 3×3 neighbourhood, opt-in land fallback, aggregators (`total_precipitation_mm`, `day_weighted_mean_temperature_c`, `day_weighted_mean`) | T; R for tp, t2m, swvl1/2/3 (swvl2/3 verified live in P02 2026-10-30) |

### 2.3 Indicators (`src/climateadapt/indicators/`)
| Path | Purpose | Evidence |
|---|---|---|
| `rainfall.py` | Percentage anomaly with explicit undefined/invalid handling | T |
| `units.py` | K→°C, mean-daily-accumulation→mm/month, days in month | T |
| `spi.py` | Thom gamma fit per calendar month, zero point mass, windows, `compute_spi`, `validate_parameters`; exceptions `InsufficientReferenceError`, `IncompleteWindowError`, `GammaFitError` | T, R |
| `spi_diagnostics.py` | KS D statistic and empirical-rank SPI beside gamma SPI | T, R |
| `temperature.py` | Thin wrapper over `window_anomaly.py` (P04); same API, fields, results | T, R |
| `window_anomaly.py` | Shared core: day-weighted window mean, exclusion-not-imputation, anomaly, standardized anomaly, mid-rank percentile; caller-supplied validity checks | T |
| `soil_moisture.py` | Soil-water wrapper ([0, 1] m3/m3 check); anomaly in m3/m3, no category labels | T, R |

### 2.4 Pipelines (`src/climateadapt/pipelines/`)
| Path | Purpose | Evidence |
|---|---|---|
| `rainfall_anomaly.py` | CHIRPS percentage anomaly with baseline exclusion rules | T, R |
| `spi.py` | CHIRPS SPI (1–48 month windows) | T, R |
| `spi_era5.py` | ERA5-Land SPI, grid-point consistency check | T, R |
| `temperature_anomaly.py` | ERA5-Land temperature anomaly | T, R |
| `era5_windows.py` | Shared window assembly (P04, KI-16): reference planning, fail-fast validation, target-first + grouped fetch, grid-point check | T |
| `soil_moisture_anomaly.py` | ERA5-Land soil-moisture anomaly, layers 1-3, same safeguards as temperature | T, R |

Note: `spi_era5.py` and `temperature_anomaly.py` used to duplicate window-assembly logic; P04 extracted it into `era5_windows.py` (KI-16 resolved) with behavior and tests unchanged.

### 2.5 API (`src/climateadapt/api/`, `schemas*.py`, `analysis.py`)
| Route | Status |
|---|---|
| `GET /health` | T |
| `POST /v1/analysis/rainfall-anomaly` (user-supplied totals; prototype) | T |
| `POST /v1/analysis/chirps-rainfall-anomaly` | T; **R (live uvicorn call, cached data)** |
| `POST /v1/analysis/chirps-spi` | T; **R (live uvicorn call, cached data)** |
| `POST /v1/analysis/era5-spi` → 202 job (P05) | T (offline; live uvicorn check not yet run) |
| `POST /v1/analysis/era5-temperature-anomaly` → 202 job (P05) | T (offline; live uvicorn check not yet run) |
| `POST /v1/analysis/era5-soil-moisture-anomaly` → 202 job (P05) | T (offline; live uvicorn check not yet run) |
| `POST /v1/analysis/environmental-bundle` → 202 job (P05) | T; **R (live uvicorn 2026-10-30: 202 + poll → succeeded, 4/4 ok, ~21 s)** |
| `GET /v1/jobs/{job_id}` (P05) | T; **R (live poll to terminal)** |

Files: `api/main.py` (factory, validation-error handler that never echoes input, domain-error handlers, CORS, lifespan), `api/dependencies.py` (`get_chirps_client`, `get_era5_client`, `get_job_store`, shutdown), `api/jobs.py` (in-memory store: bounded workers, per-job timeout, TTL), `api/bundle.py` (per-indicator statuses), `api/errors.py` (shared codes), `schemas.py`, `schemas_chirps.py`, `schemas_spi.py`, `schemas_era5.py`, `analysis.py`, `geo.py`, `docs/openapi.json` (generated contract, matches routes). **No RAG routes, no auth, no rate limiting.**

### 2.6 Scientific RAG (`src/climateadapt/rag/`, first batch)
| Path | Purpose | Evidence |
|---|---|---|
| `manifest.py` | Validated source manifest (licence status, unverified fields) | T, R |
| `models.py`, `text.py` | `Page`, `Chunk`, `RetrievedChunk`; text normalization; page/chunk labels, `section_type` | T |
| `chunking.py` | Page-aware sliding windows, drop/count of short and number-heavy windows, `verify_chunk_provenance`, printed-label carry, `section_type` tag, `max_page_span` | T (11/13 module tests; 2 failing tests are test bugs), R |
| `ingest.py` | pypdf extraction, outputs `data/corpus/processed/<doc_id>/{pages,chunks}.jsonl` + `meta.json`, /PageLabels capture, reference counts | T, R |
| `fetch.py` | Verified PDF download with candidate URLs, `%PDF-` check, size cap, one 5xx retry | T, R |
| `bm25.py`, `fusion.py`, `retrieval.py` | BM25, RRF, `Bm25Retriever`, `HybridRetriever` (hybrid has only been tested with stubs; no dense retriever exists) + `exclude_reference` filter on both | T; BM25 R |
| `citations.py` | Citations built from manifest + chunk page range + printed labels; `verify_citation` incl. label check | T |
| `evaluation.py` | Document- and page-level metrics, per-language aggregates | T, R |

### 2.7 Developer scripts (`scripts/`)
`chirps_anomaly.py`, `chirps_cli.py` (probe, series), `chirps_spi.py`, `compare_chirps_era5.py`, `era5land_cli.py`, `inspect_nc.py`, `spi_compare.py`, `spi_diagnostics.py`, `temperature_anomaly.py`, `corpus_fetch.py`, `corpus_ingest.py`, `rag_search.py`, `rag_eval.py`, `rag_eval_review.py` (P06) — all R (each appeared in pasted logs). `scripts/chirps_layout_probe.py` was ordered deleted — **confirmed deleted** (P00 audit 2026-10-30). P03 added `scripts/llm_smoke.py` (gated Baseten probe, max 5 calls; ran once 2026-10-30, exit 0). P04 added `scripts/soil_moisture_anomaly.py` (layer 1-3 anomaly CLI; one live layer-1 run 2026-10-30, exit 0). P06 added `scripts/rag_eval_review.py` (top-3 review file for the owner); `corpus_ingest.py` gained `--max-page-span`, `rag_search.py` gained `--exclude-reference` + section display.

### 2.8 Versioned corpus assets
`corpus/manifest.json` (8 documents, metadata only) and `corpus/eval/queries.json` (15 queries: 12 English, 2 French, 1 Arabic; **gold labels written by Claude from abstracts and front matter, not from page text, and never reviewed**). P06 generated git-ignored `data/corpus/eval_review.md` for that review; labels still owner-unreviewed.

### 2.9 Test support
`tests/conftest.py` (synthetic GeoTIFF factory, MockTransport factory), `tests/era5_helpers.py` (synthetic NetCDF builder, FakeDownloader), `tests/rag_helpers.py` (minimal PDF writer). 28 test modules as listed in §1, plus `test_baseten_config.py` (P03), `test_soil_moisture.py`, `test_soil_moisture_pipeline.py`, `test_window_anomaly_regression.py` (P04), and `test_api_jobs.py`, `test_api_era5.py` (P05).

## 3. Real-data verification log (CONFIRMED from owner's logs)

**CHIRPS v3.** HTTPS monthly URL pattern works (`.../monthly/global/tifs/chirps-v3.0.YYYY.MM.tif`); files ≈22 MB, 7200×2400 float32 EPSG:4326, **LZW strips, not tiled, no overviews, no nodata tag** (so the −9999 sentinel logic matters). Remote single-pixel read matched the downloaded value exactly (27.39597511291504). Download mode: 33 files ≈17 min cold; remote mode: same anomaly digits (0.5543783725454325), ≈30 s cold. File ETags/Last-Modified captured; 2014-03 was revised 2025-04-22 while the rest were 2024-11/12.

**ERA5-Land via CDS.** Authentication, licence acceptance and request fields work; NetCDF (not zip) returned, ~25 KB; coordinate `valid_time`; variable `tp` units `m`; grid at multiples of 0.1°; nearest grid point (30.4, −9.6) masked in all months; fallback to (30.5, −9.6) works. Requests took ≈20–60 s; one connection drop cost ≈5 min of automatic retry. `t2m` run succeeded (units must have been `K`). `swvl1` run succeeded with unit spelling inside the accepted set. **P00 audit 2026-10-30: exact string observed as `m**3 m**-3`** (executed `scripts/inspect_nc.py` on `504d1adaca31d5f7.nc`; CONFIRMED). **P02 2026-10-30: layers 2–3 verified live** (one single-month request each, 2024-01 at the reference point; `swvl2`/`swvl3` both `m**3 m**-3`, values 0.1384/0.1545 m3/m3, same masked-point fallback). `SOIL_WATER_UNITS` tightened to the observed spelling; see `docs/DATA_VERIFICATION.md`. **P04 2026-10-30: soil-moisture anomaly verified live** (layer 1, Jan–Mar 2024, timescale 3, reference 1991–2020, fallback to (30.5, −9.6)): window mean 0.0973, reference mean 0.1478 (sd 0.0605), anomaly −0.0505 m3/m3, standardized −0.834, percentile 0.2; 30/30 reference years used; 1 new CDS request (grouped reference; target served from cache); 2 connection drops recovered by bounded retries. Means lie in [0, 1]; values reported without wet/dry interpretation.

**RAG.** Fetch: 4 of 5 automatic downloads OK (IDDP66 22.9 MB, WR45 3.3 MB, ESSD 9.4 MB, Sci Data 9.1 MB); WMO guide fetched on P06 retry 2026-10-30 (519 KB, 24 pp, title + WMO-No. 1090 verified on p. 1, sha256 `eb3c3edf…`). Ingest results: see §5. Search and eval re-ran 2026-10-30 (BM25 only): 10/15 evaluable, 5 skipped (missing manuals), hit@1 = 1.00; canonical corpus keeps default chunking (1824 chunks, cap-2 measured at 1811).

## 4. API behavior notes (from code; UNVERIFIED beyond tests unless stated)

CHIRPS requests are synchronous. Cold CHIRPS SPI reads ≈93 values (~1 min); cold anomaly ≈33 values (~30 s). Warm-cache calls are instant. Error bodies never echo inputs. P05: new ERA5/bundle endpoints return 202 + job id (never block); jobs have a 900 s timeout, 1 h TTL, 4 workers, hard cap 1000 (503 `server_busy` when full); CORS allows the Vite dev origin from settings; lifespan closes the shared CHIRPS store and cancels queued jobs. Local paths removed from client-facing error text (result provenance still carries raw-file paths by design).

## 5. Data and documents currently available

Local caches (git-ignored, created by real runs): `data/cache/chirps_v3/remote_points/`, `data/cache/chirps_v3/monthly_global/` (33 files from earlier download mode), `data/cache/era5_land/{monthly,raw}/`, `data/corpus/raw/`, `data/corpus/processed/`.

Corpus (8 intended, 5 ingested):

| doc_id | Ingested | Pages | Empty pages | Words | Chunks (dropped short/low-alpha) |
|---|---|---|---|---|---|
| `fao-iddp66-crop-yield-response-to-water` | yes | 505 | 52 | 179,845 | 996 (0/3) |
| `fao-wr45-drought-north-africa-near-east` | yes | 266 | 6 | 103,820 | 576 (0/1) |
| `essd-2021-era5-land-reanalysis` | yes | 35 | 0 | 23,442 | 131 (0/0) |
| `scidata-2026-chirps-v3` | yes | 24 | 0 | 14,846 | 83 (0/0) |
| `fao-wr22-deficit-irrigation-practices` | **no** — manual download | | | | |
| `icarda-supplemental-irrigation-climate-smart-2018` | **no** — manual | | | | |
| `icarda-supplemental-irrigation-efficient-water-use-practice` | **no** — manual | | | | |
| `wmo-1090-standardized-precipitation-index-user-guide` | yes (P06 retry) | 24 | 4 | 7,359 | 38 (0/3) |

Retrieval evaluation so far: 10 of 15 queries evaluable, 5 skipped (q01, q03, q04, q13-fr, q15-ar — relevant manuals missing); BM25 hit@1 = 1.00 on those 10 (9 English, 1 French). **Too small to mean anything**; the one French hit is unexplained.

## 6. Partial implementations

- RAG: BM25 only. `HybridRetriever` exists but has no second real retriever. Citations show PDF index + printed label where present (KI-17 resolved 2026-10-30); reference-section filter and span cap are delivered opt-in (KI-20 tooling; default retrieval unchanged).
- ERA5-Land: temperature/precipitation/soil-water series work; precipitation, temperature, and (P04) soil-moisture layers 1–3 have analysis pipelines; (P05) all three plus a bundle are API-exposed as jobs (bundle + jobs polling verified live 2026-10-30; single-indicator POSTs offline-tested only).
- SPI: value, probability, fit parameters and descriptive diagnostics only; no category labels.
- API: CHIRPS routes (sync) + ERA5 routes and bundle (async jobs); no RAG routes, no auth, no rate limiting.

## 7. Missing components (vs. blueprint and owner goals)

- Dense retrieval (multilingual E5 + Qdrant); RAG API routes.
- Area/polygon analysis (all analyses are single-point); crop context/calendar; vegetation (Sentinel-2/NDVI); WaPOR.
- Intervention catalog, constraints, ranking, evidence strength metadata (Milestone 5).
- LLM provider adapter (Baseten), report schema, agent workflow (Milestone 6). (P03 verified the route + settings only; no adapter/agent code.)
- Scenario persistence/history, API auth and rate limiting. (P05 delivered the OpenAPI contract and CORS.)
- **React + Vite frontend** (no `frontend/` directory expected).
- Computer-vision baseline (CropHarvest) — deferred.
- MLOps: Docker/Compose, GitHub Actions CI/CD, MLflow, Optuna, Airflow, PostgreSQL/PostGIS, Prometheus, Evidently, Grafana. Of the owner's eleven named tools only Pytest and FastAPI exist.

## 8. Unresolved questions for the owner

1. Official judging rubric, weights, deadline, rules on prebuilt work, submission format.
2. Confirm target users (`PROJECT_CONTEXT.md` §2).
3. Baseten: endpoint URL, auth header/env var, rate limits and credit budget, whether tool calling/JSON-schema output is supported for the model.
4. Is Milestone 3 (CropHarvest vision) wanted, and may MLflow/Optuna be demonstrated on retrieval evaluation instead?
5. Are the three manual PDFs and a WMO mirror available?
6. ~~Is the repo under git, and are the four proposed fixes applied?~~ **Answered 2026-10-30:** yes, git repo on branch `feat/muse-code-handoff`; all four KI-01 fixes present and verified (see §1b).
7. ~~Exact `units` string in `504d1adaca31d5f7.nc` (swvl1 NetCDF).~~ **Answered 2026-10-30:** `m**3 m**-3` (observed via `scripts/inspect_nc.py`).
8. Which demo locations beyond the Moroccan reference point should be used to support "global-first" claims?

See `KNOWN_ISSUES.md` for bugs and risks.
