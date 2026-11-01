# ClimateAdapt Lab

Evidence-grounded AI agent for agricultural drought adaptation (Meta Global Developer AI
Hackathon project). **Status (verified 2026-10-30, see `docs/handoff/AUDIT_REPORT.md`):**
Milestones 0-2 are implemented (tested data connectors and precipitation/temperature
indicators). Scientific RAG first batch is partially complete (BM25 + RRF retrieval,
citations, evaluation harness; 4 of 8 corpus documents ingested; dense retrieval and RAG
API routes missing). Recommendation engine delivered 2026-10-31 (P08: versioned
catalog, deterministic constraints/ranking, `scripts/validate_catalog.py`; see
`docs/RECOMMENDATION_ENGINE.md`). Agent pipeline delivered 2026-10-31 (P10: fixed
workflow, `docs/AGENT_WORKFLOW.md`; scenario API + SQLite persistence in P11).
React input/analysis UI delivered 2026-10-31 (P12: `frontend/`, 42 Vitest tests
green; recommendations/report UI delivered 2026-10-31 (P13: cited report, ranking panel, history, Markdown export; 72 Vitest tests green).
Verified baseline (2026-10-30): 536 tests passed in 9 min 36 s, `ruff check .` clean;
details in `docs/handoff/IMPLEMENTATION_STATUS.md`, issues in `docs/handoff/KNOWN_ISSUES.md`.
Full evidence: `docs/handoff/AUDIT_REPORT.md`.

## Scientific scope and limitations

- Indicators implemented: precipitation **percentage anomaly**, **SPI** (gamma fit per calendar
  month, WMO-No. 1090), and an ERA5-Land **temperature window anomaly** (degC difference,
  standardized anomaly, empirical percentile). All are *relative to a reference period*. None
  measures drought impact, and none returns severity labels.
- The percentage anomaly is mean-based and can mislead on skewed rainfall records. SPI is more
  appropriate, but its gamma fit is not goodness-of-fit tested; `scripts/spi_diagnostics.py`
  reports how sensitive SPI is to that assumption.
- Data: CHIRPS v3 Final (monthly, 0.05 degree, 60S-60N, 1981-present) and ERA5-Land monthly
  means (0.1 degree reanalysis, 1950-present). Coverage, units, provenance, and limitations are
  returned with every result. No global validation is claimed.
- **Products can disagree.** In one real test (Jan-Mar 2024, one point) CHIRPS and ERA5-Land
  gave SPI-3 of -0.52 and -0.38 with a 0.77 yearly correlation, but quite different monthly
  totals. Use `scripts/spi_compare.py` and treat disagreement as uncertainty.
- Missing values are never converted to zero and never partially summed. Reference years with
  incomplete windows are excluded and reported, never imputed.
- ERA5-Land has no value at masked (for example sea) grid points. By default months are
  reported as missing. The opt-in `--land-fallback-km` uses the nearest valid neighbour and
  always reports the substitution.
- A point exactly on a CHIRPS cell edge or corner is flagged. Use points that are not
  multiples of 0.05 degrees.

## Setup (repo root, PowerShell)

```powershell
uv sync --extra dev
copy .env.example .env
uv run pytest
uv run ruff check .
```

The suite takes about 10 minutes (verified 9 min 36 s on 2026-10-30: 536 passed;
it builds many synthetic rasters). Optionally run in parallel: `uv run --with pytest-xdist pytest -n auto`.

## Run the API

```powershell
uv run uvicorn climateadapt.api.main:app --reload
```

Docs: http://127.0.0.1:8000/docs

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness and version |
| `POST /v1/analysis/rainfall-anomaly` | Prototype anomaly from user-supplied totals |
| `POST /v1/analysis/chirps-rainfall-anomaly` | Percentage anomaly computed from CHIRPS v3 Final |
| `POST /v1/analysis/chirps-spi` | SPI from CHIRPS v3 Final (default reference 1991-2020) |
| `POST /v1/analysis/era5-spi` | ERA5-Land SPI as a background job (202 + poll) |
| `POST /v1/analysis/era5-temperature-anomaly` | ERA5-Land temperature anomaly as a job |
| `POST /v1/analysis/era5-soil-moisture-anomaly` | ERA5-Land soil-moisture anomaly as a job (layers 1-3) |
| `POST /v1/analysis/environmental-bundle` | CHIRPS SPI + ERA5 trio as one job; per-indicator statuses |
| `GET /v1/jobs/{job_id}` | Poll a job: queued / running / succeeded / failed / timed_out |
| `POST /v1/scenarios` | Create a scenario: queue one bounded agent run (202 + ids) |
| `GET /v1/scenarios` | List stored scenarios, newest first (paginated) |
| `GET /v1/scenarios/{id}` | Retrieve bundle, ranking, report, and trace |
| `DELETE /v1/scenarios/{id}` | Delete a stored scenario |

ERA5-Land endpoints never block: each POST returns 202 with a `job_id` immediately
and the client polls `GET /v1/jobs/{job_id}` (per-job timeout 900 s, results kept
1 hour; see `CLIMATEADAPT_API_*` in `.env.example`). The bundle reports every
indicator separately (`ok` / `undefined` / `failed` / `skipped`) with its result
or typed error, provenance, limitations, and grid cells — never a composite score
or severity label. CHIRPS endpoints stay synchronous. Full contract: `docs/openapi.json`.

Scenarios (the React frontend contract): `POST /v1/scenarios` validates the
request, persists it to SQLite (`data/scenarios.sqlite3` by default), queues
one fixed-pipeline agent run, and returns 202 with `scenario_id` and `job_id`.
`GET /v1/scenarios/{id}` returns the stored input, deterministic bundle and
ranking, and either the validated report (`complete`) or the labelled fallback
(`partial`), plus the trace, problems, and warnings. History is paginated
(`limit` 1-100, `offset`). All scenario responses carry `"version": 1`; the
frontend must gate on it. Request bodies over 1 MB get 413
(`request_too_large`). Error codes: `scenario_not_found` (404), `job_not_found`
(404), `server_busy` (503), plus the analysis codes. **No authentication:**
anyone who can reach the server can create, read, and delete scenarios; do not
expose it beyond localhost without adding auth. Regenerate the contract after
any route change with `uv run python scripts/export_openapi.py`; generate the
frontend client from `docs/openapi.json` (e.g. `openapi-typescript`) rather
than hand-writing it, and keep a contract test against the `version` field.

```powershell
# Create a scenario (needs warm caches for an offline run; without a Baseten
# key the report is the labelled deterministic fallback -- no credits spent)
$body = @{
  latitude = 30.43; longitude = -9.61; target_end_month = "2024-03"
  timescale_months = 3; reference_start_year = 1991; reference_end_year = 2020
  min_reference_years = 30; land_fallback_max_km = 15.0
  query = "deficit irrigation scheduling"; top_k = 5
  crop = "wheat"; has_water_source = $true
  has_irrigation_equipment = $true; production_system = "irrigated"
  season = "2024-03"
} | ConvertTo-Json
$created = Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/scenarios `
  -Method Post -Body $body -ContentType "application/json"
$created.scenario_id; $created.job_id

# Poll the job, then read the stored result
Invoke-RestMethod http://127.0.0.1:8000/v1/jobs/$($created.job_id)
Invoke-RestMethod http://127.0.0.1:8000/v1/scenarios/$($created.scenario_id)

# History (paginated) and deletion
Invoke-RestMethod "http://127.0.0.1:8000/v1/scenarios?limit=20&offset=0"
Invoke-RestMethod http://127.0.0.1:8000/v1/scenarios/$($created.scenario_id) -Method Delete
```

## Run the frontend

Prereqs: Node 20.19+ (Vite 8; the system Node here is v16.13.1, so P12 was
built and verified with a portable Node v26.13.0 + npm 11.20.0 — see
`docs/handoff/IMPLEMENTATION_STATUS.md` §2.14). Start the API first (above),
then:

```powershell
cd frontend
copy .env.example .env   # VITE_API_BASE_URL only (public value, no secrets)
npm install
npm run dev              # strict port 5173, matching the API CORS default
```

`npm run lint`, `npm run test` (Vitest, 72 tests), `npm run build` (`tsc` +
`vite build`). After any backend route change, regenerate the typed client
with `npm run gen:api` (openapi-typescript from `docs/openapi.json`); a
contract test fails on drift.

What the app does (P12): a validated scenario form (lat/lon with coverage
hints, window, reference period, crop, water flags, ERA5 land-fallback toggle),
job progress with polling/timeout/keep-waiting, and one results card per
indicator (value, units, reference period, source + coverage, status,
limitations, provenance, fallback/cell-edge warnings) with a reference-summary
chart. No composite scores or severity labels are rendered anywhere; every API
error `type` code maps to one specific message. P13 adds the cited report (every claim with evidence links and platform-value chips, AI-vs-platform labels, fallback banner, always-visible limitations), the deterministic ranking panel (score breakdowns, unknowns, excluded reasons), scenario history with open/delete, and one-click Markdown export.
Out of scope: authentication, mobile polish.

## Demo mode

For offline or rate-limited demos, the API can serve stored real-data runs:

```powershell
$env:CLIMATEADAPT_DEMO_MODE = 'true'
uv run uvicorn climateadapt.api.main:app --reload
```

`GET /v1/demo/snapshots` lists captures; `GET /v1/demo/snapshots/{key}`
returns one. With the flag off both answer 404 (`demo_mode_disabled`).
Capture with `uv run python scripts/capture_demo_snapshot.py --key <k>
--label "<label>" --lat <lat> --lon <lon>` (deterministic, zero model calls)
into git-ignored `data/demo_snapshots/`. The frontend Demo page (`#/demo`)
renders snapshots with a "Cached real-data snapshot" banner and capture
timestamp. See `docs/DEMO_RUNS.md` (real results at four locations) and
`docs/DEMO_SCRIPT.md` (walk-through + fallback plan).

## Docker demo stack

P15. Backend image (Python 3.11 slim + `uv sync`; rasterio/scipy install from
wheels, no GDAL build; the `dense` extra is excluded) and frontend image (Node
22 build, nginx serve), orchestrated by `docker-compose.yml`. Host `./data`
(caches, corpus text, sqlite) is bind-mounted so images stay small and warm
caches are reused; `.dockerignore` keeps `data/`, `.env` files, and corpus
text out of the images. No secrets in images — copy `.env.docker.example` to
the untracked `.env.docker` for overrides (a real Baseten key belongs only
there or in the shell environment):

```powershell
docker compose up --build
```

Backend: http://127.0.0.1:8000 (`/health`, `/docs`); frontend:
http://localhost:5173 (matches the backend CORS default). The backend health
check gates the frontend start. Fresh ERA5-Land downloads inside the container
need `~/.cdsapirc` mounted read-only (commented line in the compose file);
without it, cached ERA5 + CHIRPS runs work and new CDS requests fail loudly.

Status (2026-11-01): `docker compose config --quiet` passes (Compose v5.6.0,
CONFIRMED); image build and container start were NOT run here (no Docker
daemon in this environment) — the owner must run the command above and report.
CI (`.github/workflows/ci.yml`: ruff, offline pytest, compose-config check,
frontend lint/test/build, uv + npm caching, no live APIs or secrets) is
authored and YAML-validated but has never executed on GitHub. Prometheus,
MLflow, Optuna, Evidently, Airflow, Grafana, and PostgreSQL are explicitly NOT
IMPLEMENTED (owner chose core-only on 2026-11-01; see KI-30).

## Scripts

```powershell
# CHIRPS
uv run python scripts/chirps_anomaly.py --lat 30.43 --lon -9.61 --observed-start 2024-01 --window-months 3 --baseline-start-year 2011 --baseline-end-year 2020
uv run python scripts/chirps_spi.py --lat 30.43 --lon -9.61 --target-end 2024-03 --timescale 3
uv run python scripts/chirps_cli.py probe --year 2024 --month 1

# ERA5-Land (needs CDS credentials, below)
uv run python scripts/era5land_cli.py series --variable total_precipitation --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03 --land-fallback-km 15
uv run python scripts/temperature_anomaly.py --lat 30.43 --lon -9.61 --target-end 2024-03 --timescale 3 --land-fallback-km 15
uv run python scripts/soil_moisture_anomaly.py --variable volumetric_soil_water_layer_1 --lat 30.43 --lon -9.61 --target-end 2024-03 --timescale 3 --land-fallback-km 15

# Cross-product checks and diagnostics
uv run python scripts/compare_chirps_era5.py --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03 --land-fallback-km 15
uv run python scripts/spi_compare.py --lat 30.43 --lon -9.61 --target-end 2024-03 --timescale 3 --land-fallback-km 15
uv run python scripts/spi_diagnostics.py --source chirps --lat 30.43 --lon -9.61 --target-end 2024-03 --timescale 3

# Inspect a downloaded ERA5-Land NetCDF (no network)
uv run python scripts/inspect_nc.py "data\cache\era5_land\raw\<file>.nc"

# Scientific RAG first batch (BM25 retrieval; needs an ingested corpus)
uv run python scripts/corpus_fetch.py
uv run python scripts/corpus_ingest.py
uv run python scripts/corpus_ingest.py --max-page-span 2  # optional: cap chunk page spans
uv run python scripts/rag_search.py "supplemental irrigation rainfed wheat" --top-k 5
uv run python scripts/rag_search.py "supplemental irrigation rainfed wheat" --exclude-reference
uv run python scripts/rag_eval.py
uv run python scripts/rag_eval_review.py  # writes git-ignored data/corpus/eval_review.md

# Dense retrieval (needs the dense extra + a built index).
# pyproject.toml pins torch to CPU-only builds (pytorch-cpu index, with a PyPI
# fallback on macOS where torch is CPU-only), so a fresh sync stays small and
# never pulls CUDA-enabled PyTorch unexpectedly.
uv sync --extra dev --extra dense
uv run python scripts/rag_index.py
uv run python scripts/rag_eval.py --compare
uv run python scripts/rag_eval.py --k-sweep

# Recommendation catalog (offline; checks manifest + ingested corpus)
uv run python scripts/validate_catalog.py

# Validated LLM report (one gated Baseten call; needs CLIMATEADAPT_RUN_LIVE_LLM=1
# plus a configured key, warm caches, and an ingested corpus; falls back
# deterministically when the draft is invalid -- see docs/LLM_PROVIDER_NOTES.md)
$env:CLIMATEADAPT_RUN_LIVE_LLM = "1"; uv run python scripts/llm_report.py

# Full agent run (same gate; warm caches + offline BM25 + at most one Baseten
# call; saves trace + report under git-ignored data/agent_runs/)
$env:CLIMATEADAPT_RUN_LIVE_LLM = "1"; uv run python scripts/run_agent.py
```

ERA5-Land variables: `2m_temperature`, `total_precipitation`,
`volumetric_soil_water_layer_1/2/3` (0-7, 7-28, 28-100 cm). Layer 4 is excluded because its
documented depth is contested. Soil-water *connector* support (series for layers 1-3)
exists and is tested, but the soil-moisture *anomaly pipeline* and ERA5 API routes are
delivered in P04 (pipeline) and P05 (API routes); KI-06 and KI-07 are resolved.

## CHIRPS access modes

`CLIMATEADAPT_CHIRPS_ACCESS`: `remote` (default) reads one pixel per month with HTTP range
requests (a real 33-month run took about 30 s cold; provenance stores size, ETag, and
Last-Modified). `download` fetches whole ~22 MB monthly files with SHA-256 provenance.
`CLIMATEADAPT_PREFETCH_WORKERS` (1-8) sets parallel remote reads.
`CLIMATEADAPT_ALLOW_DOWNLOADS=false` forces cache-only, reproducible runs.

## ERA5-Land credentials (one-time)

1. Create a free account at https://cds.climate.copernicus.eu and copy your personal access
   token from your profile.
2. Create `%USERPROFILE%\.cdsapirc` (in your home folder, **not** in this repository):
   ```
   url: https://cds.climate.copernicus.eu/api
   key: <PERSONAL-ACCESS-TOKEN>
   ```
3. While logged in, open the dataset page "ERA5-Land monthly averaged data from 1950 to
   present" and accept its terms of use. Requests fail until you do.

Never commit your token. Tests never need credentials or network access.
`CLIMATEADAPT_CDS_RETRY_MAX`, `CLIMATEADAPT_CDS_SLEEP_MAX_SECONDS`, and
`CLIMATEADAPT_CDS_TIMEOUT_SECONDS` bound cdsapi's retries (applied only if your installed
cdsapi exposes those options; otherwise a warning is logged).

## Error behaviour

All errors use `{"detail": [{"loc": [], "msg": "...", "type": "<code>"}]}` with codes:
`outside_coverage` (422), `data_not_available` (404), `missing_data` (422),
`insufficient_baseline` (422), `insufficient_reference` (422), `download_error` (502),
`data_integrity_error` (502). Invalid requests are 422. Unknown or expired job ids
return 404 `job_not_found`. A full job store returns 503 `server_busy` (retry shortly).
Job and bundle records reuse the domain codes above and
add `timeout` (job exceeded its budget) and `internal` (unexpected failure, generic
message, details logged server-side only). A zero baseline returns 200 with
`status: "undefined"`.

## Known limitations

Cached CHIRPS remote values are not revalidated against ETag changes (CHC revised at least one
file after release). The SPI gamma fit is not goodness-of-fit tested and there are no SPI
category labels. Still missing: dense
retrieval + RAG routes (BM25 batch exists). The soil-moisture pipeline, agent workflow, scenario persistence, and input/analysis UI are delivered (P04, P08–P12). The recommendation catalog
covers irrigation options only (v1, 3 entries; other options unranked by design).

## Verified environment and audit limits (2026-10-30)

- Verified with Python 3.11.17 (uv-managed), pytest 9.1.1, ruff 0.17.2, uv 0.13.5.
- Frontend prerequisite: Node 20.19+ is required (Vite 8), but only Node v16.13.1 is installed system-wide; P12 was built and verified with a portable Node v26.13.0 + npm 11.20.0 (untracked `node-tmp/`).
  Upgrade the system Node or keep the portable toolchain for further frontend work.
- P00 audit was offline and read-only: live CDS behavior, Baseten model access, and `.env`
  contents were deliberately not verified. No new source-code defects were found.