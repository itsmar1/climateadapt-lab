# P00 Audit Report — ClimateAdapt Lab

Date: 2026-10-30. Auditor: Muse Code (read-only pass; this file is the only change).
Branch audited: `feat/muse-code-handoff` @ `12f3ac6`. Worktree was clean before the audit.

Status words: **CONFIRMED** (observed in this session, evidence below), **CONTRADICTED**
(observed the opposite), **REPORTED** (claimed in handoff docs or logs, not re-observed),
**UNVERIFIED** (cannot be checked offline / was not checked).

## 1. Executive summary

- The repository matches the handoff description closely: all expected source, test, script,
  corpus and doc files are present; no renames detected. The baseline is **green**:
  `536 passed` in 9 min 36 s and `ruff check` clean. The four KI-01 fixes are present and
  work, so **KI-01 is resolved** and P01 has nothing to fix.
- Two handoff open questions are answered by this audit: the swvl1 NetCDF `units` string is
  exactly `m**3 m**-3` (executed `scripts/inspect_nc.py`), and the installed cdsapi 0.7.7
  exposes all three retry options (`retry_max`, `sleep_max`, `timeout`), so the app's retry
  bounds apply (read from the installed package source). Live CDS retry behavior is still
  UNVERIFIED.
- No milestone definitions exist in the repo (the blueprint was never committed), so
  milestone verdicts below map code to the handoff's implied milestones: data + indicators +
  CHIRPS API (M0–M2) are implemented and tested; RAG first batch (BM25/RRF/citations/eval)
  is implemented and tested but half the corpus is missing; dense retrieval, soil-moisture
  pipeline, ERA5/RAG API routes, recommendations, LLM adapter/agent, frontend, persistence,
  Docker/CI are all absent (no code, not partial).
- No judging rubric exists locally; all demo priorities below are provisional.
- New findings: Node v16.13.1 is installed (too old for current Vite — P12 needs a Node
  upgrade); `uv.lock` is tracked but unmentioned in the handoff; README's "retrieval not
  built yet" line is contradicted; the suite now takes 9:36, longer than both prior claims.
- Shell sandbox outage: the managed sandbox was unusable for the whole session (stuck
  Windows ACL lock, 4 failures). All commands were run via one-off unsandboxed execution
  (`require_escalated`) with read-only, offline commands only. No packages were
  installed or upgraded; `uv sync` was deliberately skipped because the venv already
  matches the lockfile.

## 2. Repository structure and git status

### 2.1 Git state (executed)

- `git status --short` before the audit: **empty (clean)**. No remote is configured
  (`.git/config` has no `[remote]` section).
- `git branch --show-current`: `feat/muse-code-handoff`. HEAD = `12f3ac6`
  ("docs: muse code handoff"); `master` = `1465834` (one commit behind; the handoff-docs
  commit exists only on this branch).
- Last 15 commits (`git log --oneline -15`), oldest first: `5706db0` ruff fixes,
  `2e589c9` CHIRPS backends + ERA5 connector, `c704c3c` land-mask fix, `d0632c6` README,
  `276bb89` SPI gamma, `b2e854c` test fix, `a4af647` ERA5 SPI + comparison, `5564c73` temp
  anomalies + CDS retries, `552c995` SPI diagnostics + soil water, `a4d9827` README,
  `4a30a7c` test fix, `cb94ab4` .gitignore, `64f8231` retrieval foundation,
  `1465834` test + ruff fixes, `12f3ac6` handoff docs. The reflog (`.git/logs/HEAD`)
  shows 6 earlier commits (initial → CHIRPS connector → anomaly pipeline → ERA5
  connector → README), 21 commits total. Commit history is consistent with the handoff
  narrative. CONFIRMED.

### 2.2 Tracked-file safety (executed)

`git ls-files` filtered for `^\.env$|^(data|frontend)/|\.pdf$|uv\.lock` returned only
`uv.lock`. So: `.env` NOT tracked, `data/` NOT tracked, no `frontend/` tracked, no PDFs
tracked, `uv.lock` IS tracked. `.gitignore` covers `.env` (line 18), `data/cache/` and
`data/corpus/` (lines 29–30). CONFIRMED. (`~/.cdsapirc` lives outside the repo and was
not touched.)

### 2.3 Worktree listing vs `IMPLEMENTATION_STATUS.md` §2 (inspected)

| Expected | Observed |
|---|---|
| `src/climateadapt/`: `__init__`, `config`, `analysis`, `geo`, `schemas*` (3), `api/` (3 incl. `__init__`), `data/` (9), `indicators/` (6), `pipelines/` (5), `rag/` (12) = 41 `.py` files | All 41 present, same paths. No `llm/`, `recommend/`, `rag/embeddings.py`, `rag/dense.py`. CONFIRMED |
| `tests/`: 28 `test_*` modules + `conftest.py`, `era5_helpers.py`, `rag_helpers.py` | All 31 present, same names. CONFIRMED |
| `scripts/`: 13 scripts | All 13 present. `chirps_layout_probe.py` confirmed deleted. CONFIRMED |
| `corpus/manifest.json`, `corpus/eval/queries.json` | Both present; nothing else under `corpus/`. CONFIRMED |
| `docs/handoff/`: 5 docs | All 5 present; no other docs (no `openapi.json`, no `DATA_VERIFICATION.md`). CONFIRMED |
| Root: `pyproject.toml`, `README.md`, `AGENTS.md`, `.env.example`, `.gitignore`, `.python-version` | All present, plus `uv.lock` (tracked, unmentioned in handoff) and local-only `.env`, `.venv/`, `data/`, `.git/`. No `technical_blueprint.txt`, `Dockerfile`, `docker-compose.yml`, `.github/`, `frontend/`. CONFIRMED |

No renamed or extra source files were found. `uv.lock` is the only tracked file the
handoff does not list (observation, not a problem).

### 2.4 Local-only data (inspected, git-ignored)

- `data/cache/chirps_v3/monthly_global/`: 33 monthly `.tif` + sidecars (2011–2020 Jan–Mar
  plus 2024 Jan–Mar); one file measured 22,243,892 bytes (~22 MB). CONFIRMED.
- `data/cache/chirps_v3/remote_points/lat30.4300_lon-9.6100/`: per-month JSON (1991+).
- `data/cache/era5_land/monthly/`: `2m_temperature/`, `total_precipitation/`
  (1991+, reference point), `volumetric_soil_water_layer_1/` (only 2024-01/02/03). No
  layer-2/3 cache dirs. CONFIRMED.
- `data/cache/era5_land/raw/`: 5 `.nc` files — 2× total precipitation, 2× 2 m temperature
  (`units` = `K`), 1× volumetric soil water layer 1 (`units` = `m**3 m**-3`), identified
  via header inspection and `inspect_nc.py` (see §9). CONFIRMED.
- `data/corpus/raw/`: at least the IDDP66 PDF (22,936,920 bytes per its meta.json);
  `data/corpus/processed/`: 4 ingested documents with `pages.jsonl`, `chunks.jsonl`,
  `meta.json` (see §8). CONFIRMED.
- `.env` exists locally and was deliberately never opened. Its contents (e.g. whether a
  Baseten key is configured) are UNVERIFIED.

## 3. Available environments

| Tool | Version (executed or inspected) |
|---|---|
| Python (`.venv`, uv-managed CPython) | 3.11.17 (`python --version`). `.python-version` = 3.11, `pyvenv.cfg` = 3.11 / uv 0.13.5. CONFIRMED |
| pytest / ruff (installed in `.venv`) | 9.1.1 / 0.17.2 (`--version` + dist-info + `uv.lock`). CONFIRMED |
| cdsapi / fastapi / httpx / starlette | 0.7.7 / 0.162.0 / 0.28.1 / 1.10.0 (`uv.lock`; cdsapi dist-info read). CONFIRMED |
| pydantic / pypdf / xarray / rasterio / numpy / scipy / netcdf4 / uvicorn | 2.14.1 / 6.21.3 / 2026.9.0 / 1.4.4 / 2.4.6 / 1.17.1 / 1.7.5.1 / 0.54.0 (`uv.lock`). CONFIRMED |
| uv | 0.13.5 (`uv --version`). CONFIRMED |
| Node / npm | v16.13.1 / 8.1.2 (`--version`). CONFIRMED — **Node 16 is end-of-life and below the Node 18+ that current Vite requires; P12 needs a Node upgrade (new finding).** |
| Docker | 29.8.2 (`docker --version`). Engine present; no Docker files exist yet. CONFIRMED |
| Frontend project | None (`frontend/` does not exist). CONFIRMED |
| Network install status | Deps already installed and matching the lockfile; `uv sync` skipped per no-install rule. CONFIRMED |

No torch / sentence-transformers / qdrant / faiss / onnx in `pyproject.toml` or
`uv.lock` (case-insensitive search, zero hits). CONFIRMED — dense retrieval has no
dependency footprint at all.

## 4. Commands executed and results

All commands were read-only and offline. The managed shell sandbox failed
(see §5.4), so each ran via one-off unsandboxed execution. `.venv` binaries were
invoked directly to avoid any implicit `uv sync` network/install step; the canonical
`uv run …` equivalents are given for re-verification.

1. Recon (exit 0):
   `git status --short` (empty), `git branch --show-current`
   (`feat/muse-code-handoff`), `git log --oneline -15` (see §2.1), `git ls-files` safety
   filter (only `uv.lock`), `--version` probes (§3), `ruff check .` → `All checks passed!`.
2. Route check (exit 0):
   `python -c "from climateadapt.api.main import app; print(sorted({r.path for r in app.routes}))"`
   → `['/docs', '/docs/oauth2-redirect', '/health', '/openapi.json', '/redoc',
   '/v1/analysis/chirps-rainfall-anomaly', '/v1/analysis/chirps-spi',
   '/v1/analysis/rainfall-anomaly']` (4 app routes + 4 FastAPI docs routes).
   (First delivery of this output was lost in transit; the command was re-run
   unchanged and the output above is verbatim from the re-run.)
3. NetCDF check (exit 0): `python scripts/inspect_nc.py
   data\cache\era5_land\raw\504d1adaca31d5f7.nc` — variable `swvl1`,
   `units` = `m**3 m**-3`, 3×3 grid, 3 time steps (2024-01/02/03); grid point
   (30.4, −9.6) NaN in all months; neighbour (30.5, −9.6) = 0.070251 / 0.110382 /
   0.112000. Full output in §9. Local-file read, no network.
4. Full suite (exit 0): `python -m pytest -q --tb=short` →
   `536 passed, 1 warning in 576.54s (0:09:36)`. The 1 warning is the known
   `StarletteDeprecationWarning` (httpx vs `starlette.testclient`, KI-04).
5. Post-report `git status --short` (exit 0) → only `?? docs/handoff/AUDIT_REPORT.md`
   (plus `docker --version` → `Docker version 29.8.2, build 7fc2dff`). This proves no
   other file was created or modified by the audit.

NOT run, with reason: `uv sync --extra dev` (user forbade installs; env already synced);
any script needing network/credentials (`corpus_fetch`, `chirps_*`, `era5land_cli`,
`temperature_anomaly`, `spi_*`, `compare_chirps_era5`, live API server); anything reading
`.env` or `~/.cdsapirc`.

## 5. Test and static-check results

- **PASSED**: full suite `536 passed` (exit 0, 576.54s); `ruff check .`
  (`All checks passed!`); API route import check (8 paths incl. docs routes);
  `scripts/inspect_nc.py` on the swvl1 file (exit 0).
- **FAILED**: none.
- **SKIPPED**: none (no skips/deselects; `-ra` reported nothing skipped).
- **BLOCKED / COULD NOT RUN**: initially everything shell-based — the sandbox failed 4
  times with `windows_elevated ... ACL publication lock
  Global\TbhWindowsSandboxAclPublication ... wait timed out after 120000 ms`
  (a stuck machine-global lock, unrelated to this repo). Worked around via one-off
  unsandboxed execution; nothing remains unrunnable. If the sandbox is still broken
  later, re-verify with (repo root, PowerShell):
  `uv run ruff check .`, `uv run pytest`, and
  `uv run python -c "from climateadapt.api.main import app; print(sorted({r.path for r in app.routes}))"`.

## 6. Milestone implementation status

No milestone definitions exist in the repo (`technical_blueprint.txt` was never
committed), so the mapping below follows the handoff's implied milestones and the README
status line. "Complete" = implemented + tested; real-data re-verification was out of
scope for this offline audit.

- **M0 (project setup/config)** — COMPLETE (CONFIRMED): `pyproject.toml` + `uv.lock`,
  `.env.example`, `src/climateadapt/config.py` (`Settings`, `CLIMATEADAPT_` prefix),
  tests layout, ruff/pytest config all present and exercised by the green suite.
- **M1 (CHIRPS connector + precipitation indicators + API)** — COMPLETE (CONFIRMED):
  `data/chirps.py` (download store, `sample_dataset`, −9999 sentinel, boundary flag),
  `data/chirps_remote.py` (GDAL `/vsicurl/` single-pixel reads, per-point cache,
  prefetch), `indicators/rainfall.py`, `indicators/spi.py` (Thom gamma fit),
  `pipelines/rainfall_anomaly.py`, `pipelines/spi.py`, 3 CHIRPS API routes + `/health`.
  Real-data behavior is REPORTED (past logs) with local cache files corroborating that
  runs happened; not re-executed here.
- **M2 (ERA5-Land connector + temperature/SPI indicators)** — COMPLETE as CLI
  (CONFIRMED): `data/era5_land.py` (VARIABLES for t2m/tp/swvl1-3, per-month cache,
  3×3 neighbourhood, opt-in ≤25 km land fallback, aggregators), `data/cds_client.py`
  (signature-checked retry bounds), `indicators/temperature.py`,
  `indicators/spi_diagnostics.py`, `indicators/units.py`, `pipelines/spi_era5.py`,
  `pipelines/temperature_anomaly.py`, CLI scripts. ERA5 API exposure does not exist
  (expected — P05 scope).
- **M3 (computer vision)** — NOT STARTED (CONFIRMED): no CV code, deps, or docs beyond
  handoff mentions; deferral decision still pending with the owner.
- **M4 (scientific RAG, first batch)** — PARTIALLY COMPLETE (CONFIRMED): manifest,
  fetch, ingest, page-aware chunking + provenance verification, BM25, RRF,
  `Bm25Retriever`/`HybridRetriever`, citations, evaluation harness all implemented and
  tested (details in §8). Missing within M4: dense E5 + Qdrant retriever (no code at
  all), RAG API routes, 4 of 8 corpus documents, page-level gold annotations, printed
  page labels. `HybridRetriever` is generic/inert without a second retriever.
- **M5 (recommendations) / M6 (agent + LLM)** — NOT STARTED (CONFIRMED): no
  `recommend/` or `llm/` packages, no catalog, no provider adapter, no report schema.
- **Frontend / persistence / MLOps** — NOT STARTED (CONFIRMED): no `frontend/`,
  no database, no Docker/CI files; of the eleven owner-named MLOps tools only pytest
  and FastAPI are present.

## 7. Verification of the four KI-01 fixes

All four proposed fixes are present in the code (inspected) and proven working by the
green suite (executed). KI-01 is resolved.

1. `DEFAULT_CHUNKING_PARAMS` constant in `src/climateadapt/rag/chunking.py:37` and used
   as the `chunk_document` default at line 64. CONFIRMED.
2. Same constant imported (`src/climateadapt/rag/ingest.py:19`) and used as the
   `ingest_document` default (line 108). CONFIRMED. (`ruff check` passing confirms both
   B008 findings are gone.)
3. Tamper test edits a word *inside* the chunk: `tests/test_rag_text_chunking.py:62`
   (`pages[0].text.replace("w0030", "w9999")`). CONFIRMED. Rationale holds:
   `verify_chunk_provenance` (`chunking.py:118-150`) re-derives chunk text from page
   text, so only an in-chunk edit invalidates it — the test was wrong, the source was
   right.
4. Number-heavy test uses `* 20` (exactly two 100-word windows):
   `tests/test_rag_text_chunking.py:82`. CONFIRMED — the old `* 25` miscounted
   (125 prose words); the test was wrong, the source was right.

## 8. RAG implementation assessment

| Component | Path | Verdict |
|---|---|---|
| Manifest (validated, licence status, `unverified_fields`) | `rag/manifest.py`, `corpus/manifest.json` | Implemented + tested. 8 docs: 5 automatic, 3 manual; licences 2 stated / 3 verified / 3 unverified (WMO, ESSD, SciData). CONFIRMED |
| Ingestion (pypdf extract → `pages/chunks.jsonl` + `meta.json`) | `rag/ingest.py`, `scripts/corpus_ingest.py` | Implemented + tested; empty/scanned-PDF and per-page-failure warnings present. CONFIRMED |
| Fetch (verified PDF download, `%PDF-` check, size cap) | `rag/fetch.py`, `scripts/corpus_fetch.py` | Implemented + tested (MockTransport). No retry-on-5xx (P06 scope). CONFIRMED |
| Page-aware chunking + provenance verify | `rag/chunking.py`, `rag/text.py`, `rag/models.py` | Implemented + tested (220/40/30/0.45 defaults); dropped short/low-alpha windows counted, never silent; `chunk_index` gaps visible. CONFIRMED |
| BM25 (hand-rolled, Lucene-style idf, no stemming) | `rag/bm25.py` | Implemented + tested incl. hand-checked formula tests. CONFIRMED |
| RRF | `rag/fusion.py` | Implemented + tested. `DEFAULT_RRF_K = 60` with an explicit in-code caveat that k=60 is unverified recollection (line 3-5) — consistent with KI-21. CONFIRMED |
| Retrievers | `rag/retrieval.py` | `Bm25Retriever` real; `HybridRetriever` generic but has no second real retriever. Tests use `StubRetriever` for hybrid (`tests/test_rag_bm25_fusion.py:128-173`). CONFIRMED |
| Citations | `rag/citations.py` | Implemented + tested, but pages are PDF indices only (`format_pages`, line 33-34) — KI-17 stands. CONFIRMED |
| Evaluation harness | `rag/evaluation.py`, `scripts/rag_eval.py`, `corpus/eval/queries.json` | Implemented + tested: hit@k, doc_recall@k, MRR, page-level variants, per-language splits, skip-and-report for missing docs. 15 queries (12 en / 2 fr / 1 ar); zero `relevant_pages` entries (page-level annotations absent). `relevance_basis` strings confirm abstract/ToC/front-matter basis. With the 4 ingested docs, 8 queries are evaluable and 7 skip — matches the handoff exactly. CONFIRMED |
| Dense E5 + Qdrant | — | MISSING entirely: no `rag/embeddings.py`, no `rag/dense.py`, no `scripts/rag_index.py`, no related deps. Not "partial" — absent. CONFIRMED |
| RAG API routes | — | MISSING (no RAG routes in `api/main.py`). CONFIRMED |

Ingested-corpus cross-check (local `meta.json` files): IDDP66 505 pp / 996 chunks /
22.9 MB; WR45 266 pp / 576 chunks / 3.3 MB; ESSD 35 pp / 131 chunks / 9.4 MB; SciData
24 pp / 83 chunks / 9.1 MB — all match `IMPLEMENTATION_STATUS.md` §5 exactly. CONFIRMED.
`chunks.jsonl` spot-check shows `chunk_id`/`page_start`/`page_end`/`word_count`/`text_sha256`
provenance on every chunk. A first-chunk read shows chunk 0 spanning PDF pages 1–4,
illustrating KI-20's wide-range concern. 3 manual PDFs + WMO guide still missing. CONFIRMED.

## 9. Climate-data and NetCDF verification

- `scripts/inspect_nc.py` EXISTS (71 lines) and RUNS (exit 0, offline). CONFIRMED.
- Exact `units` for `data/cache/era5_land/raw/504d1adaca31d5f7.nc`: **`m**3 m**-3`**
  (both `units` and `GRIB_units` attributes of variable `swvl1`,
  "Volumetric soil water layer 1"). Observed by execution — **KI-05's core question is
  answered**; no guessing involved. Verbatim head of output:

  ```
  dimensions:        {'valid_time': 3, 'latitude': 3, 'longitude': 3}
  latitude: [30.5 30.4 30.3]
  longitude: [-9.7 -9.6 -9.5]
  variable 'swvl1': dims=('valid_time', 'latitude', 'longitude') shape=(3, 3, 3) dtype=float32
    attributes: {... 'GRIB_units': 'm**3 m**-3', ... 'units': 'm**3 m**-3', ...}
    share of NaN values overall: 0.444
    time step 2024-01-01:            (30.5,-9.6)=0.070251 ... (30.4,-9.6)=NaN ...
    time step 2024-02-01:            (30.5,-9.6)=0.110382 ...
    time step 2024-03-01:            (30.5,-9.6)=0.112000 ...
  ```

  The full grid (observed in the §4 item-3 run) shows (30.4, −9.6) NaN in all 3 months and the whole
  −9.7 column NaN — consistent with a land–sea mask (the file's own history attribute
  confirms a real 2026-10-27 CDS conversion). The fallback values match the handoff's
  0.070/0.110/0.112. KI-10's mask explanation is corroborated by the data pattern but
  still not confirmed against ERA5-Land documentation. The observed spelling is one of
  the four in `SOIL_WATER_UNITS` (`data/era5_land.py:145`), so no code change is
  strictly required; P02 may still tighten the set (layers 2–3 unverified live).
- Raw-file inventory (header inspection): `19dd3da20aa42dbf.nc` + `fc4c0e7c0a49a0eb.nc`
  = total precipitation; `6fe2b9a95886f907.nc` + `c934f5f84541c7b2.nc` = 2 m temperature
  with `units` = `K` (CONFIRMED, was previously implied-by-passing-run).
- Monthly cache JSONs independently record `"raw_units": "m**3 m**-3"` for swvl1
  (e.g. `data/cache/era5_land/monthly/volumetric_soil_water_layer_1/.../2024-01.json:11`).
- Soil-moisture anomaly pipeline: MISSING — no `pipelines/soil_moisture_anomaly.py`, no
  `scripts/soil_moisture_anomaly.py`. Only data-layer support exists (`VARIABLES`
  entries for layers 1–3 with 0–7/7–28/28–100 cm depths, `day_weighted_mean`,
  `tests/test_era5_soil_moisture.py` with 18 connector-level tests). Layer 4 absent by
  design. KI-06 stands. CONFIRMED.
- ERA5 indicator endpoint: MISSING — no ERA5 routes in `api/main.py`; ERA5 indicators
  are CLI-only (`scripts/era5land_cli.py`, `temperature_anomaly.py`, `spi_compare.py`,
  `spi_diagnostics.py`). KI-07 stands. CONFIRMED.
- No severity labels or composite scores anywhere: `indicators/` + `pipelines/`
  contain only explicit refusals ("NOT a severity class", "no SPI category labels").
  CONFIRMED.
- cdsapi retry options (KI-08): the installed `.venv/.../cdsapi/api.py:289-310`
  declares `timeout=60`, `retry_max=500`, `sleep_max=120` as explicit `__init__`
  keywords, and the retry loop (lines 651-655) honours `self.retry_max` /
  `sleep_max`. Therefore `supported_options` in `data/cds_client.py:24-40` classifies
  all three app bounds as supported and they ARE passed. The signature half of KI-08
  is CONFIRMED resolved; live retry behavior remains UNVERIFIED (needs a real failing
  request, out of scope for P00).

## 10. Frontend, backend and API assessment

- Frontend: `frontend/` does not exist; no `package.json`, no Vite/React/TS anywhere.
  No Streamlit code or dependency exists either — "Streamlit" appears only in
  `AGENTS.md` (prohibition) and the handoff docs (history + cleanup reminder). README
  has no Streamlit mentions. KI-27 confirmed as stated. CONFIRMED.
- Backend (`src/climateadapt/api/main.py`, 184 lines, fully read): exactly the 4
  documented routes (verified by import: `/health`, `/v1/analysis/rainfall-anomaly`,
  `/v1/analysis/chirps-rainfall-anomaly`, `/v1/analysis/chirps-spi`, plus FastAPI's
  own `/docs`, `/redoc`, `/openapi.json`). Single error shape with the 7 documented
  codes (lines 43-51), matching README; validation handler never echoes input
  (lines 61-76). CONFIRMED.
- Gaps (all CONFIRMED by inspection): no CORS/`CORSMiddleware` (zero hits in `src/`);
  no auth, no rate limiting; no lifespan/shutdown handling for the `lru_cache`d shared
  CHIRPS client (`api/dependencies.py:11-13`); synchronous endpoints (cold CHIRPS SPI
  reads ~93 values); no ERA5/RAG/scenario/job routes; no `docs/openapi.json`. The
  download-store offline error embeds a local cache path (`data/chirps.py:267`
  `...is not in the local cache ({path})...`) — KI-28's local-path point, still present.
- API input conventions hold: all 37 Pydantic models in `src/` set `extra="forbid"`
  (schemas.py subclasses inherit it from `_StrictModel`); strict numerics and
  finite-value guards in `data/coverage.py:42-57`, `data/periods.py:20-28`.
- Layering (P00 step 8): `indicators/` imports only stdlib + scipy + the pure
  `data.periods.YearMonth` value type — no FastAPI, no network, no `rag/`/`api/`
  imports. CONFIRMED clean. Tests touch the network only via `httpx.MockTransport`
  and `fastapi.testclient.TestClient` (6 hits, all fakes); every helper docstring
  states synthetic-only data. CONFIRMED.
- Config vs `.env.example`: `config.py` matches `.env.example` except `http_user_agent`
  (config default `climateadapt-lab/0.1 (research prototype)`) has no `.env.example`
  entry — minor documentation gap (new finding).

## 11. Baseten configuration and externally unverified capabilities

- The approved model ID `meta-models/muse-spark-open-1026` appears ONLY in
  documentation (`AGENTS.md:74`, `PROJECT_CONTEXT.md`, `KNOWN_ISSUES.md` KI-25,
  `MUSE_CODE_TASK_PROMPTS.md` P03/P09). A case-insensitive search for
  baseten/spark/meta-models/openai/anthropic/llm/qdrant/torch/e5 across the repo finds
  zero hits in `src/`, `tests/`, `scripts/`, `corpus/`, `pyproject.toml`, `uv.lock`,
  `.env.example`, or `README.md` (only benign hits: an "never delegated to an LLM"
  docstring and a regex `.fullmatch`). CONFIRMED: **no provider code, no provider
  settings, no key handling, no smoke script exist**. No substitution of the model ID
  was made or needed — there is nothing to substitute.
- All of the following require separate verification (P03) and are UNVERIFIED: Baseten
  base URL / endpoint path, auth header and env-var name, request/response schema,
  tool/function-calling support, JSON-schema/structured-output support, streaming,
  context and output limits, rate limits, credit cost, error codes. No live call was
  attempted (forbidden in P00).
- `.env` was never opened, so whether a Baseten key is already configured locally is
  UNVERIFIED and must stay that way until P03 (key handling must follow the
  secret-safe rules in AGENTS.md §8).

## 12. Documentation inconsistencies

1. README status line ("The retrieval, recommendation, agent, and UI layers are not
   built yet", `README.md:4-6`) — CONTRADICTED for retrieval: the RAG first batch is
   implemented, tested, and has 4 ingested documents.
2. README has no RAG section/commands (`corpus_fetch/ingest`, `rag_search/eval`) —
   CONFIRMED stale (as the handoff already notes).
3. README "suite takes about 4–5 minutes" (`README.md:40-41`) — CONTRADICTED: this
   session observed 9:36 (owner's last log: 7:44). Understated in both cases.
4. README "Soil water, retrieval, recommendation, agent, and UI layers are still to
   do" (`README.md:122`) — partly stale: soil-water *connector* support (layers 1–3,
   18 tests, cached real swvl1 run) exists; only the anomaly *pipeline* + API are
   missing. Needs the same nuance for retrieval.
5. `IMPLEMENTATION_STATUS.md` file inventory — CONFIRMED accurate (all paths exist,
   no renames); omissions: tracked `uv.lock` (new observation) and the confirmed
   deletion of `chirps_layout_probe.py` (handoff already marks it "ordered deleted" —
   now confirmed gone).
6. `IMPLEMENTATION_STATUS.md` test counts — total 536 CONFIRMED (identical collection
   count, now 536 passed vs 534+2); per-module breakdown was not individually
   re-verified (only the total + zero failures observed) — treat per-module numbers
   as REPORTED-compatible.
7. `KNOWN_ISSUES.md` spot-check: KI-01 resolved (see §7); KI-04 still present
   (warning observed verbatim); KI-05 core answered (§9); KI-08 signature half
   resolved (§9); KI-17/18/19/20/21 (citations, missing docs, gold set, bibliography
   chunks, no dense retrieval) all CONFIRMED still open; KI-25/26/27/28/29/30/31/32
   CONFIRMED still open; KI-02 (repo may differ) is now retired by this audit —
   the repo matches the conversation code; KI-34 (utf-8 only in RAG scripts)
   CONFIRMED (`sys.stdout.reconfigure` in exactly the 4 RAG scripts).
8. `queries.json` self-documents its own weakness ("NOT derived from page text",
   line 3) — the handoff's KI-19 description is CONFIRMED by the artifact itself.
9. `AGENTS.md` — all checkable claims verified: src layout, pytest/ruff config
   (`E,F,I,B,UP`, line-length 100), `extra="forbid"` everywhere (37/37),
   BM25+RRF-implemented / dense-planned, no frontend, no Streamlit in code.
10. Handoff real-data figures spot-checked against local artifacts: swvl1 fallback
    values (0.070/0.110/0.112 ✓ via `inspect_nc.py`), ingest page/chunk counts
    (505/996, 266/576, 35/131, 24/83 ✓ via `meta.json`), PDF sizes
    (22.9/3.3/9.4/9.1 MB ✓), CHIRPS ~22 MB files ✓. CHIRPS/ERA5 SPI and anomaly
    numbers were NOT re-executed — REPORTED (with cache files corroborating that the
    runs happened).

## 13. Prioritized defects and blockers

**Verified defects (all CONFIRMED, with evidence):**

1. (High) No verified end-to-end path exists: ERA5/RAG indicators are unreachable from
   the API, and there is no frontend — a demo currently requires CLI + warm caches.
   Evidence: §10 route list; §6 missing list.
2. (High) No judging rubric, deadline, or submission rules locally (searched whole
   repo; only "unknown" references). Blocks demo-scope decisions. Owner action.
3. (High) Baseten integration is at zero: no code, no config, every capability
   UNVERIFIED. Agent architecture (tool-calling vs fixed pipeline) cannot be chosen
   until P03. Evidence: §11.
4. (Medium) Retrieval quality is unevaluated in any meaningful sense: 8 evaluable
   queries, unreviewed document-level labels, no page annotations, 4/8 docs missing,
   BM25-only (no cross-lingual). Evidence: §8.
5. (Medium) Node v16.13.1 installed — current Vite requires Node 18+. Must upgrade
   before P12. (New finding.)
6. (Medium) API not frontend-ready: no CORS, no job/polling pattern, synchronous
   long calls, no shutdown hook, one error message leaks a local path
   (`data/chirps.py:267`). Evidence: §10.
7. (Medium) Soil-moisture anomaly pipeline + ERA5 endpoints missing (KI-06/KI-07).
8. (Low) `StarletteDeprecationWarning` on every run (KI-04, cause still uninvestigated;
   harmless but noisy).
9. (Low) Suite takes 9:36 and is growing (KI-03; was 7:44).
10. (Low) README stale in four places (§12.1–12.4); `http_user_agent` missing from
    `.env.example` (§10).

**Unresolved blockers needing the owner (unchanged from handoff §8):** official
rubric/deadline/rules; 3 manual PDFs (+ WMO retry/mirror); Baseten endpoint/auth/budget
answers; gold-label review; catalog-source approval; M3 go/no-go; demo locations.

**No new code defects** were found in the audited source; the suite is green and ruff
is clean.

## 14. Recommended next task (P01 close-out, then P03-docs)

P01-as-written ("fix verified problems") has nothing to fix — the baseline is already
green. Do not run a no-op P01. Instead:

**Next task: P01-closeout + README/handoff refresh (small, offline, no live calls).**

1. Re-run `uv run pytest` and `uv run ruff check .`, record final lines.
2. Update `IMPLEMENTATION_STATUS.md` §1 (536 passed, ruff clean, 9:36, date) and the
   uv.lock / deleted-probe-file notes; mark KI-01 resolved, KI-05 core answered
   (`m**3 m**-3`, observed 2026-10-30), KI-08 signature confirmed for cdsapi 0.7.7
   (live behavior still open), KI-02 retired by this audit.
3. Update README: fix the status line (RAG batch 1 exists), add the 4 RAG script
   commands, correct suite time to ~10 min, nuance the soil-water line.
4. Add the Node-18+ requirement note for P12 (this report §3) to `KNOWN_ISSUES.md`
   (new KI) and the P12 prompt prerequisites.

Acceptance: full suite green (quote final line); ruff clean; `git diff` touches only
docs; every changed claim carries fresh CONFIRMED evidence; no secrets added.
Verify: `uv run pytest`, `uv run ruff check .`, `git status --short`.

After that, run **P03 against current Baseten documentation first** (no key needed to
read docs; key + budget needed before any smoke call), in parallel with owner actions
(PDFs, rubric, gold-label review). P02's remaining live part (swvl2/3 units, ≤4 CDS
requests) can follow whenever CDS access is convenient.

## 15. Finding-status ledger

- CONFIRMED (this session, executed): green suite 536/536; ruff clean; 4 routes;
  worktree clean; branch/commits; tracked-file safety; Python/pytest/ruff/node/uv
  versions; `swvl1` units `m**3 m**-3`; masked grid point NaN; fallback values;
  t2m units `K`; all four KI-01 fixes working.
- CONFIRMED (this session, inspected): all 41 src / 31 test / 13 script / corpus /
  doc paths; no frontend/CI/Docker/LLM/dense/recommend/CV code; no Streamlit in code;
  no secrets in tracked code; `extra="forbid"` 37/37; clean layering; Mock-only tests;
  no CORS/auth/jobs; local path in one error message; cdsapi 0.7.7 options exist;
  manifest/eval-set contents; ingest table; Stub-only hybrid tests; RRF k=60 caveat;
  no torch/qdrant deps; Node 16.
- CONTRADICTED: README "retrieval not built" and "4–5 minute suite"; any implication
  that the 2 test failures or 2 ruff errors persist (all fixed).
- REPORTED (prior logs, corroborated by local caches but not re-executed): CHIRPS/ERA5
  SPI + anomaly values, request latencies, fetch outcomes (4/5 + WMO 503), BM25 hit@1
  = 1.00 on 8 queries, per-module test counts, Baseten model access/credits.
- UNVERIFIED: live CDS retry behavior; swvl2/3 units; all Baseten API capabilities;
  `.env` contents; per-module test-count breakdown; multi-location behavior; anything
  requiring network, credentials, or model credits.

---

*P00 acceptance check: this report contains real command output (§4–5, §9); the only
intended filesystem change is this file (post-write `git status` below proves it);
statements are labeled CONFIRMED / CONTRADICTED / REPORTED / UNVERIFIED throughout.
Deliberately deviated from P00 step 4 (`uv sync`) per the user's no-install rule —
see §4. No code, config, test, or doc (other than this report) was modified; no
network, credential, or model-credit use occurred.*
