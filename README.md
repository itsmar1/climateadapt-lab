# ClimateAdapt Lab

Evidence-grounded AI agent for agricultural drought adaptation (Meta Global Developer AI
Hackathon project). **Status (verified 2026-10-30, see `docs/handoff/AUDIT_REPORT.md`):**
Milestones 0-2 are implemented (tested data connectors and precipitation/temperature
indicators). Scientific RAG first batch is partially complete (BM25 + RRF retrieval,
citations, evaluation harness; 4 of 8 corpus documents ingested; dense retrieval and RAG
API routes missing). Recommendation engine delivered 2026-10-31 (P08: versioned
catalog, deterministic constraints/ranking, `scripts/validate_catalog.py`; see
`docs/RECOMMENDATION_ENGINE.md`). Agent and UI layers: not started.
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

ERA5-Land endpoints never block: each POST returns 202 with a `job_id` immediately
and the client polls `GET /v1/jobs/{job_id}` (per-job timeout 900 s, results kept
1 hour; see `CLIMATEADAPT_API_*` in `.env.example`). The bundle reports every
indicator separately (`ok` / `undefined` / `failed` / `skipped`) with its result
or typed error, provenance, limitations, and grid cells — never a composite score
or severity label. CHIRPS endpoints stay synchronous. Full contract: `docs/openapi.json`.

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
```

ERA5-Land variables: `2m_temperature`, `total_precipitation`,
`volumetric_soil_water_layer_1/2/3` (0-7, 7-28, 28-100 cm). Layer 4 is excluded because its
documented depth is contested. Soil-water *connector* support (series for layers 1-3)
exists and is tested, but the soil-moisture *anomaly pipeline* and ERA5 API routes are
still missing (see `docs/handoff/KNOWN_ISSUES.md` KI-06, KI-07).

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
category labels. Still missing: soil-moisture anomaly pipeline (connector exists), dense
retrieval + RAG routes (BM25 batch exists), agent, and UI. The recommendation catalog
covers irrigation options only (v1, 3 entries; other options unranked by design).

## Verified environment and audit limits (2026-10-30)

- Verified with Python 3.11.17 (uv-managed), pytest 9.1.1, ruff 0.17.2, uv 0.13.5.
- Frontend prerequisite: Node.js 18+ is required for current Vite, but only Node v16.13.1
  is installed — upgrade Node before any frontend work.
- P00 audit was offline and read-only: live CDS behavior, Baseten model access, and `.env`
  contents were deliberately not verified. No new source-code defects were found.