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
| M2 (ERA5-Land connector + temperature/SPI indicators) | **Complete as CLI** | `data/era5_land.py`, `data/cds_client.py`, `indicators/temperature.py`, `indicators/spi_diagnostics.py`, `indicators/units.py`, `pipelines/spi_era5.py`, `pipelines/temperature_anomaly.py`, CLI scripts. ERA5 API exposure added (P05: temperature/SPI/bundle endpoints). |
| M3 (computer vision) | **Classical baseline done 2026-11-01 (P16)** | `src/climateadapt/vision/` + scripts + 35 tests (see §2.18); logreg/rf on CropHarvest v14, MLflow-tracked, evaluated on 543k held-out rows (see `docs/VISION_BASELINE.md`). Neural model + Optuna deferred by recorded decision. |
| M4 (scientific RAG, first batch) | **Partially complete** | Implemented + tested: manifest, fetch, ingest, page-aware chunking + provenance verification, BM25, RRF, `Bm25Retriever`/`HybridRetriever`, citations, evaluation harness. Missing within M4: RAG API routes, 3 of 8 corpus documents, page-level gold annotations for 5 queries. Dense E5 + Qdrant + hybrid delivered (P07). |

M5 (recommendations) / M6 (agent + LLM), frontend, persistence, and Docker/CI are all
**not started** — no code, not partial (AUDIT_REPORT §6). **P08 update 2026-10-31:**
M5 engine is **implemented + tested** (`src/climateadapt/recommend/`, 3-entry v1 catalog,
`scripts/validate_catalog.py`, 80 offline tests; see §2.10). **P09 update 2026-10-31:**
M6 adapter half is **implemented + tested** (`src/climateadapt/llm/`, 51 offline tests,
one gated live call with fallback served; see §2.11). **P10 update 2026-10-31:**
M6 agent workflow is **implemented + tested** as a fixed pipeline
(`src/climateadapt/agent/`, 22 offline tests, one gated live run with
validator-rejected draft → fallback; see §2.12 and `docs/AGENT_WORKFLOW.md`).
**P11 update 2026-10-31:** scenario persistence is **implemented + tested** (SQLite store + CRUD API, direct-call probe green; TestClient suite written but sandbox-unrunnable; see §2.13). **P12 update 2026-10-31:** React input/analysis UI is **implemented + tested** (`frontend/`, 42 Vitest tests green, tsc/eslint/build clean, verified against real backend outputs; see §2.14). **P13 update 2026-10-31:** cited report + ranking UI is **implemented + tested** (report sections with evidence links, ranking breakdowns, history, Markdown export; 72/72 Vitest green, gates clean, verified against real outputs; see §2.15). **P14 update 2026-10-31:** reproducible demo is **implemented + tested** (integration tests, demo mode + snapshots, Playwright e2e 3/3, real runs at 4 locations; see §2.16). **P15 update 2026-11-01:** Docker + CI are **authored** (Dockerfiles, compose stack, CI workflow; compose-config check passes) but image build, container start, and CI's first GitHub run are UNVERIFIED (see §2.17). **P16 update 2026-11-01:** classical CropHarvest vision baseline delivered (see §2.18).

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
| `cds_client.py` | Builds a `cdsapi.Client` passing only retry/timeout options the installed signature exposes | T; signature half CONFIRMED for cdsapi 0.7.7 (P02 2026-10-30: all three options exist and are passed); live recovery observed (P04: 2 drops recovered, §3); full retry matrix still U |
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
| `POST /v1/scenarios` → 202 + ids (P11) | U (14 TestClient tests written; sandbox blocks sockets so none ran — see KI-34 note; equivalent direct-call probe passed) |
| `GET /v1/scenarios` paginated (P11) | U (same as above) |
| `GET /v1/scenarios/{id}` (P11) | U (same as above) |
| `DELETE /v1/scenarios/{id}` → 204 (P11) | U (same as above) |

Files: `api/main.py` (factory, validation-error handler that never echoes input, domain-error handlers, CORS, lifespan), `api/dependencies.py` (`get_chirps_client`, `get_era5_client`, `get_job_store`, shutdown), `api/jobs.py` (in-memory store: bounded workers, per-job timeout, TTL), `api/bundle.py` (per-indicator statuses), `api/errors.py` (shared codes), `schemas.py`, `schemas_chirps.py`, `schemas_spi.py`, `schemas_era5.py`, `analysis.py`, `geo.py`, `docs/openapi.json` (generated contract, matches routes). **No RAG routes, no auth, no rate limiting.**

### 2.13 Scenario API + SQLite persistence (P11 2026-10-31)
| Path | Purpose | Evidence |
|---|---|---|
| `api/schemas_scenarios.py` | Versioned (`"version": 1`) created/summary/list/detail contracts; detail separates bundle, ranking, report, trace | U (probe-verified, TestClient suite unrunnable in sandbox) |
| `api/store.py` | `ScenarioStore` protocol + thread-safe stdlib-SQLite store (WAL, `user_version` migrations, schema v1) | T (sync tests ran green) + probe |
| `api/scenarios.py` | Background worker (run agent → persist terminal outputs; deleted-mid-run safe) + row assembly | U (probe-verified, TestClient suite unrunnable in sandbox) |
| `api/body_limit.py` | Body-cap middleware (1 MB default → 413 `request_too_large`, CORS headers kept) | U (probe-verified incl. exact 413 shape) |
| `api/dependencies.py` | `get_scenario_store`, `get_agent_deps`, `get_llm_provider` (live Baseten or honest unavailable stand-in → labelled fallback) | U (probe-verified via direct route calls) |
| `scripts/export_openapi.py` | Deterministic `docs/openapi.json` regeneration (11 paths) | R (ran 2026-10-31) |

Tests: `tests/test_api_scenarios.py` (14 TestClient tests: lifecycle, restart on a temp DB, failed runs, validation shape, pagination, delete, 503 rollback, no-key partial, CORS preflight, 413, openapi routes) — written but never run green in this sandbox (socket block, KI-34 note); a throwaway direct-call probe verified the same behaviors and passed. Standalone `POST /v1/evidence/search` deliberately NOT added: the report already carries cited evidence, and an extra endpoint would widen unauthenticated corpus-text exposure. No auth, no rate limiting (documented limitation).

### 2.14 React input/analysis UI (`frontend/`, P12 2026-10-31)
| Path | Purpose | Evidence |
|---|---|---|
| `src/api/schema.d.ts` | Types generated from `docs/openapi.json` (`npm run gen:api`, openapi-typescript 7.13.0) | T (contract test guards drift) |
| `src/api/client.ts`, `errors.ts` | openapi-fetch client (contract-version gate, 30 s timeout); every backend `type` code → one specific message | T |
| `src/api/presenters.ts` | Pure bundle-entry → card view models; defensive narrowing; no severity language (test-enforced) | T |
| `src/components/` | `ScenarioForm` (validated inputs, coverage hints, fallback toggle), `JobProgress` (2 s poll, timeout + keep-waiting), `ResultsView` + `IndicatorCard` + `ReferenceChart` (summary band, never per-year points), `StatusBadge`; `App` hash routing | T |
| `src/test/fixtures.ts` | Synthetic fixtures + fresh-Response `mockFetch` | T |

Gates (CONFIRMED 2026-10-31, portable Node v26.13.0 + npm 11.20.0 — system Node is v16.13.1): `tsc` exit 0, `eslint .` exit 0, **42/42 Vitest tests green** (8 files), `vite build` → `dist/` in 8.4 s. Each tool's current docs were verified before use (Vite 8, Vitest 5, RTL, ESLint flat + typescript-eslint, openapi-typescript 7.x).
Real-backend verification (CONFIRMED, $0 spent): this sandbox blocks `listen()`/`socketpair()` (WinError 10013), so no TCP server or browser run was possible here; instead the exact `run_scenario_job` callable ran in-process on the reference scenario (form-default body validates; downloads off; production no-key `UnavailableProvider`): `partial` in 24.1 s, 4/4 indicators ok (CHIRPS SPI −0.517, ERA5 SPI −0.375, temp +2.22 °C, soil −0.0505 m³/m³), labelled `deterministic-fallback` with `[provider-auth]`. That real 122 KB `ScenarioDetail` rendered through the real `ResultsView` in a throwaway test (4 cards, exact values, fallback banner, no severity text) — passed, then deleted with all other probes. In-browser check and `vite dev` serving remain UNVERIFIED here; the owner runs `uv run uvicorn climateadapt.api.main:app --reload` plus `cd frontend; npm run dev` (strict port 5173 = API CORS default).
P13 delivered 2026-10-31 (see §2.15); auth and mobile polish remain out of scope.

### 2.15 Cited report + ranking UI (P13 2026-10-31)
| Path | Purpose | Evidence |
|---|---|---|
| `src/api/reportPresenters.ts` | Evidence E-numbering, trace chips (unresolved ids stay visible), score breakdowns, rubric level names, exact-"unknown" echoes, verbatim number formatting | T |
| `src/api/export.ts` | Pure `reportToMarkdown` (all 9 sections + ranking context) + thin download glue | T |
| `src/components/ReportView.tsx`, `StatementView.tsx`, `EvidenceView.tsx`, `Echo.tsx` | Report sections; claims with evidence chips, tool-output refs, platform-value chips; citations verbatim + pages/URL/licence/unverified flags; AI-vs-platform labels | T |
| `src/components/RecommendationPanel.tsx` | Deterministic scores with component tables, evidence strength, unknowns, excluded reasons, ranking warnings/limitations | T |
| `src/components/HistoryView.tsx` | Paginated history with open/delete (two-step confirm), status badges, on-demand problem details | T |

Gates (CONFIRMED 2026-10-31, portable Node v26.13.0): `tsc` exit 0, `eslint .` exit 0, **72/72 Vitest green** (13 files), `vite build` ✓, repo `ruff check .` clean.
Real-backend verification (CONFIRMED, $0): in-process `run_scenario_job` on the reference scenario (`partial` in 5.7 s): 2 ranked tied at 0.750 (level single_source, 7 unknowns each), 1 excluded with 2 reasons, fallback report with 5 evidence items. A throwaway test rendered the real ranking + report (exact scores, contributions, citations, Unknown badges, the "not interpreted as drought severity" disclaimer) and exported real Markdown (all 9 sections) — 3/3 passed, then deleted with all probes. In-browser check still UNVERIFIED (sandbox socket block); the owner runs the two servers.
Design notes: title/authors/year render inside the verbatim formatted citation (the API exposes no separate fields and the UI parses nothing — no new backend capability per P13 scope); evidence chips are scroll buttons because hash links would fight the hash router; the naive "no severity words" page assertion was replaced for real data by a drought-label-pattern check after the backend's own "not interpreted as drought severity" disclaimer tripped it.

### 2.16 Reproducible demo + e2e (P14 2026-10-31)
| Path | Purpose | Evidence |
|---|---|---|
| `tests/test_integration_workflow.py` | Store → agent → detail with fakes only at the network boundary (4 tests) | T, green |
| `src/climateadapt/api/demo.py`, `scripts/capture_demo_snapshot.py` | Snapshot store + capture CLI (deterministic, $0) | T |
| `GET /v1/demo/*` + `demo_mode_disabled`/`demo_snapshot_not_found` | Demo endpoints (13 OpenAPI paths) | T direct green; TestClient written, sandbox-blocked |
| `frontend/e2e/`, `playwright.config.ts` | Playwright 1.64.1 + system Chrome, file:// bundle, mocked HTTP (3 tests) | T, green |
| `frontend/src/components/DemoView.tsx` | Snapshot list + bannered results | T |
| `docs/DEMO_RUNS.md`, `docs/DEMO_SCRIPT.md` | Real results at 4 locations + walk-through | D |

Gates (CONFIRMED 2026-10-31): backend integration 4/4 green; demo direct tests 6/6 green; frontend 79/79 Vitest green (14 files), tsc/eslint clean, `vite build` ✓; Playwright 3/3 green (system Chrome, file:// + route mocks, `--allow-file-access-from-files`); `ruff check .` clean. Full `pytest`: green except the pre-existing TestClient socket block (5 API files incl. the 2 new demo HTTP tests — written for the owner, failing here on WinError 10013 like all TestClient suites since P11).
Real-data runs (CONFIRMED, $0 LLM): reference 4/4 ok; Punjab ERA5 ok via fresh CDS with CHIRPS blocked by sandbox egress; Norway CHIRPS `outside_coverage` + ERA5 ok via fresh CDS; Atlantic ERA5 `missing_data` on the masked point. All four captured as snapshots; details, failure modes, and non-claims in `docs/DEMO_RUNS.md`. KI-14 resolved within its stated scope.

### 2.17 Reproducible containers + CI (P15 2026-11-01)
| Path | Purpose | Evidence |
|---|---|---|
| `Dockerfile` | Backend image: python:3.11-slim, uv 0.13.5 `sync --locked` (wheels only, no GDAL build; `dense` extra excluded), uvicorn on 8000 | U (authored; build never run — no daemon here) |
| `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore` | Node 22 build → nginx static serve; `VITE_API_BASE_URL` build arg | U (same) |
| `docker-compose.yml`, `.dockerignore`, `.env.docker.example` | Demo stack: health-gated frontend, host `./data` bind-mount, optional `.cdsapirc` mount, secret-free context | T (`docker compose config --quiet` exit 0, Compose v5.6.0, CONFIRMED 2026-11-01) |
| `.github/workflows/ci.yml` | Backend (ruff, offline pytest, compose-config check) + frontend (lint/test/build) jobs with uv/npm caching; no live APIs or secrets | U (authored + YAML-validated; never executed on GitHub) |

Gates (CONFIRMED 2026-11-01): `docker compose config --quiet` exit 0. Image builds, container starts, health-check calls, and CI's first GitHub execution are all UNVERIFIED — the owner must run `docker compose up --build` and watch CI's first run. Owner chose core-only on 2026-11-01: Prometheus, MLflow, Optuna, Evidently, Airflow, Grafana, PostgreSQL explicitly NOT IMPLEMENTED (KI-30). (P16 addendum 2026-11-01: MLflow tracking now runs for the vision baseline only, outside `uv.lock` — see §2.18.)

### 2.18 CropHarvest vision baseline (P16 2026-11-01)
| Path | Purpose | Evidence |
|---|---|---|
| `src/climateadapt/vision/` | Minimal CropHarvest-data loader (stdlib geojson + h5py), mean/std aggregation, logreg/RF baselines, numpy metrics + bootstrap CIs, MLflow adapter, run manifests | T (35 offline tests green; tool parts skip without vision tools), R (real v14 run) |
| `scripts/vision_download.py`, `scripts/vision_baseline.py` | Zenodo download (size+md5 verified) + reproducible train/eval CLI (exit 0) | R (labels 113,892 rows; 87,465 train files; 6 test grids) |
| `docs/VISION_BASELINE.md` | Protocol, sources, results, limitations | D |

Results (CONFIRMED 2026-11-01, train 20,000 seeded / test 543,055 evaluable): logreg pooled acc 0.5619 / macro-F1 0.5594 (MLflow `b537f8db…`); rf 0.7972 / 0.7895 (MLflow `652be435…`); per-file + crop-general metrics with 95% CIs in the doc and in git-ignored `data/cropharvest/reports/`. The `cropharvest` PyPI package is deliberately unused (pinned 2021 deps conflict with pandas 3.x/xarray); vision tools live in the local `.venv` only, not in `pyproject.toml`/`uv.lock` (owner follow-up: add a `vision` extra + `uv lock` on a networked machine). Neural model + Optuna deferred by recorded decision. Outputs are isolated from recommendations by design.

### 2.19 Prompt registry + one repair attempt (P18 2026-11-01)
| Path | Purpose | Evidence |
|---|---|---|
| `llm/prompts.py` | `format_registry_block` (exact allowed ids/values/dates + worked `numbers[]` example + banned invented schemes), `build_repair_request` (capped problems + draft excerpt), `format_evidence_block` full-`Citation` rendering, `build_report_request(registry_block=…)` | T (15 new fake-provider tests green) |
| `llm/prompts/report_{system,user}.txt` | Verbatim-copy rules, allowed-ids-only rule, renamed TOOL DATA labels (`bundle-json`/`ranking-json`; old labels were the P10 draft's fake ids) | T |
| `agent/schemas.py`, `agent/workflow.py` | `AgentConfig.max_repair_attempts` (0/1, default 0); repair inside validate (re-validated identically, fallback on failure); prompt built with registry block + full citations | T |
| `scripts/run_agent.py` | `--repair 1 --max-llm-calls 2` defaults (single-call via `--repair 0 --max-llm-calls 1`) | T (gate) |
| `docs/LLM_PROVIDER_NOTES.md` §5–§6 | P18 `max_tokens` decision (16000 kept: `stop` observed, no verified higher limit), $0.00 spent, owner retry command, judge env-var table | D |
| `tests/test_llm_prompt_repair.py` | Registry content, verbatim citation fields, historic failure classes still rejected, repair success/failure/no-repair-default, fallback self-validation | T, green |

Result: acceptance path (b) — honest negative. No live call was made (gate off), so no draft has been accepted yet (KI-35 stays open). Timing: saved warm trace shows the ~2 min run is LLM-dominated (draft 92.1 s of 97.4 s, 94.6%); per-stage wall-clock times already ship in `trace.stages`, so the job progress payload was deliberately left unchanged (no breaking API change).

### 2.20 Fresh-clone judge path (P19 2026-11-01)
| Path | Purpose | Evidence |
|---|---|---|
| `demo/snapshots/` + `demo/README.md` | 3 audited real-data snapshots tracked (reference-morocco, trondelag-norway, atlantic-ocean); punjab-india excluded (sandbox proxy address in its CHIRPS error text) | T (new validation + no-corpus-text tests green) |
| `api/demo.py`, `config.py`, `api/main.py` | Default snapshot dir is now tracked `demo/snapshots/`; override still wins; route description + contract regenerated | T |
| `Dockerfile`, `docker-compose.yml` | `COPY demo ./demo` so the image serves snapshots; compose comment updated | U (no daemon here; owner runs `docker compose up --build`) |
| `scripts/verify_fresh_clone.ps1` | Clone → sync → demo-mode servers → probe `/health` + `/v1/demo/*`; `-SkipServers` for restricted sandboxes | Partially run: parses + executes; clone fails here only on sandbox git ownership, sync on blocked PyPI — owner runs full |
| `tests/test_integration_workflow.py` | `test_missing_corpus_yields_typed_warning_not_a_crash`: evidenceless partial with `[retrieval-empty]`, findings/ranking intact | T, green |
| README, DEMO_RUNS, DEMO_SCRIPT, SUBMISSION_CHECKLIST | "Add your model key" (§6 facts only + Meta-API owner hook), corpus/CDS zero-key notes, tracked paths | D |

Fresh-clone audit (CONFIRMED): git-ignored demo needs are corpus PDFs/text, `data/` caches, CDS + Baseten credentials; without them a clone serves `/health`, live CHIRPS reads, typed ERA5 `download_error`s, evidenceless partials — and, since P19, the full zero-key demo from tracked snapshots. Remaining owner-run: full `verify_fresh_clone.ps1`, TestClient suites, docker build, CI.

### 2.21 Interactive map + video-ready results UI (P20 2026-11-02)
| Path | Purpose | Evidence |
|---|---|---|
| `api/geo.ts`, `components/GeoMap.tsx` | Pure geo helpers (CHIRPS band, presets, `fallbackPoints` from entry `land_fallback`) + Leaflet map (click/drag pick, band shading, request/used markers, reduced-motion, screen-reader list) | T (11 new unit tests green) + real-Chrome e2e |
| `components/ScenarioForm.tsx` | Map picker two-way synced with inputs, 4 snapshot presets, outside-band note | T |
| `components/ResultsView.tsx`, `IndicatorCard.tsx` | Summary strip + section anchors, results map with used grid points + backend distances, collapsed problem groups, per-card details with counts; report limitations stay open | T |
| `components/JobProgress.tsx` | Stage list with honest overall-status-only note, cached-vs-cold durations, "Use a captured demo" link | T |
| `index.css` | Earth/water restyle (teal accent, clay markers, serif display + system-ui), responsive, focus-visible, `prefers-reduced-motion` | T (rendered in e2e shots) |
| `e2e/map.spec.ts`, `e2e/screenshots.spec.ts`, `e2e/fixtures.ts` | Real-Leaflet click/preset/band tests, results-map + collapsed-problem + severity-guard test, 5 README/video screenshots | T, green |
| `docs/screenshots/*.png` | 5 committed screenshots (form, outside-band, progress, results, report) | D |

Gates (CONFIRMED 2026-11-02, portable Node v26.13.0): `eslint .` exit 0; **96/96 Vitest green** (16 files, 77.65 s); `tsc` exit 0 via `vite build` ✓ in 16.43 s (JS 440.58 kB / gzip 132.44 kB — Leaflet accounts for ~180 kB raw over the P-final 283 kB bundle); **7/7 Playwright green** (1.4 min, system Chrome, file:// + route mocks). No backend changes (suite not re-run). One Vitest attempt failed first on worker-spawn timeouts (box load, not assertions; clean re-run green) and Playwright needed `TEMP`/`TMP` redirected to `node-tmp/pw-tmp` (sandbox blocks the system temp; see KI-34).
Library record (CONFIRMED from installed manifests + official docs read 2026-11-02): `leaflet` 1.9.4 (BSD-2-Clause), `react-leaflet` 5.0.0 + `@react-leaflet/core` 3.0.0 (**Hippocratic-2.1** — not permissive; see KI-36), `@types/leaflet` 1.9.22 (MIT); React 19 peers (`react`/`react-dom` ^19, `leaflet` ^1.9.0) satisfied by the tree (React 19.3.1). Tiles are key-free OSM standard tiles with on-map attribution per the Tile Usage Policy; no geocoding; no CSP exists (`index.html`, `nginx.conf`), so none was updated. Screenshots show blank tile backgrounds because `tile.openstreetmap.org` times out in this sandbox (CONFIRMED by direct fetch); markers, shading, controls, and attribution render — the owner can re-capture on a networked machine (command in README).

### 2.22 Validator identifier fix + efficacy prompt rules (P22 2026-11-02)
| Path | Purpose | Evidence |
|---|---|---|
| `llm/validator.py` | Narrow bug fix: `DATASET_IDENTIFIER_RE` exempts `ERA5`/`ERA5-Land`/`CHIRPS v3` digits from the numeral scan; length-preserving strip maps matches back; `undeclared-number`/`efficacy-claim` quote offending sentence + matched phrase | T (5 new tests green) |
| `llm/prompts.py`, `llm/prompts/report_system.txt` | Ranked narratives may only restate score/echoes/evidence (effect verbs banned) + compliant example; dataset-name guidance; repair keeps per-problem evidence (500-char budget) | T (2 new tests green) |
| `agent/trace.py`, `agent/workflow.py` | Trace keeps `draft_text`/`repair_text` verbatim for debugging (no credentials involved) | T (2 new tests green + e2e accept test) |
| `data/agent_runs/run-20261102T141454Z.json` | Owner live run of the P18 prompt + repair: 2 calls, 91 s, 61698/24625 tokens, problems 44 → 7 | R (saved files in repo, git-ignored) |

Diagnosis (CONFIRMED offline): H1 CONFIRMED — the five `'5'` hits are the validator matching the `ERA5`/`ERA5-Land` dataset name (`_strip_known` only strips full `data_source` echoes; only ERA5 findings flagged; the exact problem string reproduced on a synthetic draft). H2 CONFIRMED as mechanism (`efficacy-claim` fires only on an efficacy-regex match in a ranked narrative); the exact repair phrase is unrecoverable because the trace did not keep the repair output (now fixed). **Validator changed: yes, one narrow bug fix** (identifier digits exempt; bare numbers, resolutions, years, invented ids, altered citations, and real effect claims still rejected, all test-pinned). Before/after on the synthetic reproduction: `valid=False` + `[undeclared-number] ... numeral '5'` → `valid=True`. Gates: focused llm/agent suites green (103 tests), ruff clean; full suite `84 failed, 802 passed, 1 skipped` — the same 84 pre-existing sandbox socket-blocked API failures (KI-34, zero assertion failures), +10 new P22 tests all green. Live acceptance still UNVERIFIED (KI-35 stays open; owner retry budget at most 2 runs × 2 calls).

### 2.6 Scientific RAG (`src/climateadapt/rag/`, first batch)
| Path | Purpose | Evidence |
|---|---|---|
| `manifest.py` | Validated source manifest (licence status, unverified fields) | T, R |
| `models.py`, `text.py` | `Page`, `Chunk`, `RetrievedChunk`; text normalization; page/chunk labels, `section_type` | T |
| `chunking.py` | Page-aware sliding windows, drop/count of short and number-heavy windows, `verify_chunk_provenance`, printed-label carry, `section_type` tag, `max_page_span` | T (11/13 module tests; 2 failing tests are test bugs), R |
| `ingest.py` | pypdf extraction, outputs `data/corpus/processed/<doc_id>/{pages,chunks}.jsonl` + `meta.json`, /PageLabels capture, reference counts | T, R |
| `fetch.py` | Verified PDF download with candidate URLs, `%PDF-` check, size cap, one 5xx retry | T, R |
| `bm25.py`, `fusion.py`, `retrieval.py` | BM25, RRF, `Bm25Retriever`, `HybridRetriever` (P07: fuses real BM25 + dense; RRF untouched) + `exclude_reference` filter on both | T; BM25 R |
| `citations.py` | Citations built from manifest + chunk page range + printed labels; `verify_citation` incl. label check | T |
| `embeddings.py`, `dense.py` (P07) | E5-small-only wrapper (prefixes, L2 norm, lazy torch); Qdrant-local `DenseRetriever` with fingerprints + idempotent indexing | T, R |
| `evaluation.py` | Document- and page-level metrics, per-language aggregates | T, R |

### 2.7 Developer scripts (`scripts/`)
`chirps_anomaly.py`, `chirps_cli.py` (probe, series), `chirps_spi.py`, `compare_chirps_era5.py`, `era5land_cli.py`, `inspect_nc.py`, `spi_compare.py`, `spi_diagnostics.py`, `temperature_anomaly.py`, `corpus_fetch.py`, `corpus_ingest.py`, `rag_search.py`, `rag_eval.py`, `rag_eval_review.py` (P06), `rag_index.py` (P07) — all R (each appeared in pasted logs). `scripts/chirps_layout_probe.py` was ordered deleted — **confirmed deleted** (P00 audit 2026-10-30). P03 added `scripts/llm_smoke.py` (gated Baseten probe, max 5 calls; ran once 2026-10-30, exit 0). P04 added `scripts/soil_moisture_anomaly.py` (layer 1-3 anomaly CLI; one live layer-1 run 2026-10-30, exit 0). P06 added `scripts/rag_eval_review.py` (top-3 review file for the owner); `corpus_ingest.py` gained `--max-page-span`, `rag_search.py` gained `--exclude-reference` + section display. P07 added `scripts/rag_index.py` (fingerprinted dense build); `rag_eval.py` gained `--retriever/--compare/--k-sweep`. P08 added `scripts/validate_catalog.py` (catalog vs manifest + ingested corpus; exit 0 on no errors). Also present: `scripts/export_openapi.py`, `scripts/llm_report.py`, `scripts/run_agent.py`, `scripts/capture_demo_snapshot.py` (demo snapshots), `scripts/vision_download.py` + `scripts/vision_baseline.py` (P16).

### 2.8 Versioned corpus assets
`corpus/manifest.json` (8 documents, metadata only) and `corpus/eval/queries.json` (15 queries: 12 English, 2 French, 1 Arabic; **gold labels written by Claude from abstracts and front matter, not from page text, and never reviewed**). P06 generated git-ignored `data/corpus/eval_review.md` for that review; labels still owner-unreviewed.

### 2.9 Test support
`tests/conftest.py` (synthetic GeoTIFF factory, MockTransport factory), `tests/era5_helpers.py` (synthetic NetCDF builder, FakeDownloader), `tests/rag_helpers.py` (minimal PDF writer). 55 test files (counted 2026-11-01; §1's "28 modules" predates P09–P16), plus `test_baseten_config.py` (P03), `test_soil_moisture.py`, `test_soil_moisture_pipeline.py`, `test_window_anomaly_regression.py` (P04), and `test_api_jobs.py`, `test_api_era5.py` (P05), and `test_rag_dense.py` (P07), plus `tests/recommend_helpers.py` and `test_recommend_{schema,constraints,ranking,service,validate}.py` (P08, 80 tests, all offline/synthetic).

### 2.10 Recommendation engine (`src/climateadapt/recommend/`, P08 2026-10-31)
| Path | Purpose | Evidence |
|---|---|---|
| `schema.py`, `catalog.json` | Versioned catalog (v1, 3 entries); every applicability attribute nullable; benefit/cost/risk `"unknown"` unless cited; `loader.py` loads the packaged file offline | T |
| `evidence.py` | Evidence-strength rubric (0 needs_evidence / 1 single-source / 2 multi-source) + manifest-grounded citation formatting | T |
| `constraints.py` | 5 hard constraints (`needs_evidence`, `no_water_source`, `no_irrigation_equipment`, `production_system_mismatch`, `crop_not_applicable`); unknowns recorded, never excluding | T |
| `ranking.py` | Weighted score (0.5 evidence + 0.3 indicator-availability + 0.2 fit); full breakdown per option; ties by id | T |
| `service.py`, `validate.py` | `recommend()` entry point (ranked/excluded/unknowns/evidence/warnings/limitations); offline catalog validation | T |

Catalog v1: `deficit-irrigation` + `irrigation-scheduling` supported by IDDP66 pp. 22/70 and 25/66; `supplemental-irrigation` is `needs_evidence` (ICARDA docs not ingested). No LLM, no invented figures. Details: `docs/RECOMMENDATION_ENGINE.md`.

### 2.11 LLM adapter and validated reports (`src/climateadapt/llm/`, P09 2026-10-31)
| Path | Purpose | Evidence |
|---|---|---|
| `provider.py` | `LLMProvider` protocol; `BasetenProvider` (verified Chat Completions API only: bounded retries/backoff, timeouts, 429/529 handling, secret-safe logging, usage incl. cached tokens); `FakeProvider` | T |
| `report.py` | Versioned report schema (summary, findings, evidence, ranked, excluded, limitations, assumptions, coverage, provenance) + deterministic tool-output registry with bundle/ranking builders | T |
| `validator.py` | Client-side draft validation: schema, known evidence/tool ids, citations rebuilt verbatim + `verify_citation`, prose numerals traced to registry values, mandatory limitations/provenance, bans on severity labels / efficacy claims / currency+percent | T |
| `fallback.py` | Deterministic fallback report (fixed templates, labelled `deterministic-fallback`, no AI text) | T |
| `prompts.py`, `prompts/*.txt` | Versioned prompt templates with an explicit instruction hierarchy; retrieved text wrapped as escaped untrusted data | T |
| `service.py` | `generate_report`: one draft call, strict validation, labelled fallback on any failure | T |
| `scripts/llm_report.py` | Gated one-call live report (warm-cache bundle + offline BM25 + ranking + 1 Baseten call) | T (gate), R (1 call 2026-10-31: HTTP 200, 46.6 s, 26965/4000 tokens, `finish_reason=length` → empty draft → fallback served and re-validated clean; ≈$0.051) |

Tests: `tests/test_llm_provider.py`, `tests/test_report_schema.py`, `tests/test_report_validator.py` + `tests/report_helpers.py` (51 offline tests, all synthetic; injection, tampered chunks, altered numbers, timeout/rate-limit, and fallback paths covered). No agent graph/tool loop (P10 scope).

### 2.12 Fixed agent pipeline (`src/climateadapt/agent/`, P10 2026-10-31)
| Path | Purpose | Evidence |
|---|---|---|
| `schemas.py` | `AgentScenario` (validated run request), `AgentConfig` (hard limits), `AgentDeps` (injected data, no globals) | T |
| `tools.py` | 4 thin typed tools: `get_environmental_bundle`, `retrieve_evidence` (BM25 / hybrid), `rank_adaptation_options`, `validate_report` | T |
| `workflow.py` | `run_agent`: fixed 7-stage pipeline (validate → bundle → retrieval → ranking → draft → validate → finalize); `complete`/`partial`/`failed` outcomes; step/tool/LLM/token/timeout limits + loop detection | T |
| `trace.py` | `RunTrace` (stages, tool calls, verdicts, usage; no secrets, no passage text) | T |
| `scripts/run_agent.py` | Gated live end-to-end run (warm caches + offline BM25 + ≤1 call) | T (gate), R (1 call 2026-10-31: full draft produced, 44 validator problems → fallback served; 97 s, 26965/15087 tokens ≈$0.098; fallback re-validated clean, retrieval reproducible) |

Fixed pipeline by recorded decision (LangGraph 1.2.19 checked via PyPI 2026-10-31, not adopted — see `docs/AGENT_WORKFLOW.md`). Tests: `tests/test_agent_tools.py` + `tests/test_agent_workflow.py` (22 offline tests: happy path, limit enforcement, failure injection, validator rejection, trace completeness). **P18 update 2026-11-01:** prompt now states the exact registry vocabulary + worked example + verbatim citation fields, and at most one repair attempt is supported (`max_repair_attempts`, default 0; see §2.19). No model draft accepted yet (KI-35 stays open; no live call in P18). **P22 update 2026-11-02:** owner live run (2 calls, 44 → 7 problems) diagnosed offline; narrow validator identifier fix + efficacy prompt rules + repair evidence + trace drafts (see §2.22); acceptance still open.

## 3. Real-data verification log (CONFIRMED from owner's logs)

**CHIRPS v3.** HTTPS monthly URL pattern works (`.../monthly/global/tifs/chirps-v3.0.YYYY.MM.tif`); files ≈22 MB, 7200×2400 float32 EPSG:4326, **LZW strips, not tiled, no overviews, no nodata tag** (so the −9999 sentinel logic matters). Remote single-pixel read matched the downloaded value exactly (27.39597511291504). Download mode: 33 files ≈17 min cold; remote mode: same anomaly digits (0.5543783725454325), ≈30 s cold. File ETags/Last-Modified captured; 2014-03 was revised 2025-04-22 while the rest were 2024-11/12.

**ERA5-Land via CDS.** Authentication, licence acceptance and request fields work; NetCDF (not zip) returned, ~25 KB; coordinate `valid_time`; variable `tp` units `m`; grid at multiples of 0.1°; nearest grid point (30.4, −9.6) masked in all months; fallback to (30.5, −9.6) works. Requests took ≈20–60 s; one connection drop cost ≈5 min of automatic retry. `t2m` run succeeded (units directly observed as `K`; see DATA_VERIFICATION.md). `swvl1` run succeeded with unit spelling inside the accepted set. **P00 audit 2026-10-30: exact string observed as `m**3 m**-3`** (executed `scripts/inspect_nc.py` on `504d1adaca31d5f7.nc`; CONFIRMED). **P02 2026-10-30: layers 2–3 verified live** (one single-month request each, 2024-01 at the reference point; `swvl2`/`swvl3` both `m**3 m**-3`, values 0.1384/0.1545 m3/m3, same masked-point fallback). `SOIL_WATER_UNITS` tightened to the observed spelling; see `docs/DATA_VERIFICATION.md`. **P04 2026-10-30: soil-moisture anomaly verified live** (layer 1, Jan–Mar 2024, timescale 3, reference 1991–2020, fallback to (30.5, −9.6)): window mean 0.0973, reference mean 0.1478 (sd 0.0605), anomaly −0.0505 m3/m3, standardized −0.834, percentile 0.2; 30/30 reference years used; 1 new CDS request (grouped reference; target served from cache); 2 connection drops recovered by bounded retries. Means lie in [0, 1]; values reported without wet/dry interpretation.

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

Retrieval evaluation so far: 10 of 15 queries evaluable, 5 skipped (q01, q03, q04, q13-fr, q15-ar — relevant manuals missing); BM25 hit@1 = 1.00 on those 10 (9 English, 1 French). **Too small to mean anything**; the one French hit is unexplained. P07: dense + hybrid also 1.00 everywhere (ceiling-flat, exploratory); see `docs/RAG_EVALUATION.md`.

## 6. Partial implementations

- RAG: BM25 default + E5-small dense (Qdrant local, fingerprinted) + RRF hybrid (P07); comparison exploratory, no proven gain. Citations show PDF index + printed label where present (KI-17 resolved 2026-10-30); reference-section filter and span cap are delivered opt-in (KI-20 tooling; default retrieval unchanged).
- ERA5-Land: temperature/precipitation/soil-water series work; precipitation, temperature, and (P04) soil-moisture layers 1–3 have analysis pipelines; (P05) all three plus a bundle are API-exposed as jobs (bundle + jobs polling verified live 2026-10-30; single-indicator POSTs offline-tested only).
- SPI: value, probability, fit parameters and descriptive diagnostics only; no category labels.
- API: CHIRPS routes (sync) + ERA5 routes and bundle (async jobs); no RAG routes, no auth, no rate limiting.
- Recommendations (P08 2026-10-31): engine complete and tested, but the catalog is intentionally tiny (2 supported irrigation entries); growth needs owner-supplied sources (KI-18 manuals, KI-26).

## 7. Missing components (vs. blueprint and owner goals)

- ~~Dense retrieval (multilingual E5 + Qdrant);~~ **Delivered 2026-10-31 (P07)** — this bullet was stale; corrected P21. Still missing: RAG API routes.
- Area/polygon analysis (all analyses are single-point); crop context/calendar; vegetation (Sentinel-2/NDVI); WaPOR.
- ~~Intervention catalog, constraints, ranking, evidence strength metadata (Milestone 5).~~ **Delivered 2026-10-31 (P08):** engine + 3-entry v1 catalog; catalog *growth* still needs owner-approved sources.
- ~~LLM provider adapter (Baseten), report schema, agent workflow (Milestone 6).~~ **Adapter + schema + validator delivered 2026-10-31 (P09):** `src/climateadapt/llm/` with 51 offline tests and one gated live call (fallback served, see §2.11). **Agent workflow delivered 2026-10-31 (P10):** fixed pipeline in `src/climateadapt/agent/` with 22 offline tests and one gated live run (see §2.12).
- ~~Scenario persistence/history, API auth and rate limiting.~~ **Persistence delivered 2026-10-31 (P11):** scenario CRUD + SQLite history (see §2.13). API auth and rate limiting still missing (documented limitation, KI-28).
- ~~**React + Vite frontend** (no `frontend/` directory expected).~~ **Input/analysis screens delivered 2026-10-31 (P12):** form, polling, indicator cards + chart (see §2.14). Recommendations/report UI delivered 2026-10-31 (P13, see §2.15).
- ~~Computer-vision baseline (CropHarvest) — deferred.~~ **Delivered 2026-11-01 (P16, classical only):** logreg + random forest on CropHarvest v14 with MLflow tracking and 543k-row held-out eval (see §2.18, `docs/VISION_BASELINE.md`). Neural model, Optuna and the `vision` lockfile extra remain future work.
- ~~MLOps: Docker/Compose, GitHub Actions CI/CD, MLflow, Optuna, Airflow, PostgreSQL/PostGIS, Prometheus, Evidently, Grafana. Of the owner's eleven named tools only Pytest and FastAPI exist.~~ **Partially delivered 2026-11-01 (P15):** Dockerfiles + compose stack + CI workflow authored (`docker compose config` CONFIRMED; image builds, container starts, and CI's first execution UNVERIFIED — owner must run). **P21 update 2026-11-02:** backend image built + `/health` OK is now REPORTED by the owner (after the `libexpat1`/`libgomp1` fix, commit `670d74c`, present in the tree); frontend image build, compose-run serving, and CI's first execution remain UNVERIFIED. Prometheus, MLflow, Optuna, Evidently, Airflow, Grafana, PostgreSQL explicitly NOT IMPLEMENTED per the owner's core-only decision (see §2.17, KI-30).

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
