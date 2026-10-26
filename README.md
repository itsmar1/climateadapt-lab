# ClimateAdapt Lab

Evidence-grounded AI agent for agricultural drought adaptation (Meta Global Developer AI
Hackathon project). **Status: Milestone 1 in progress** - tested CHIRPS v3 and ERA5-Land
point connectors and a CHIRPS-based rainfall-anomaly endpoint.

## Scientific scope and limitations

- Implemented indicator: a simple precipitation **percentage anomaly**
  `((observed_total - baseline_mean) / baseline_mean) * 100`. It is a prototype, **not** a
  calibrated drought index, and must not be used alone to classify drought severity. It is
  mean-based and can mislead on skewed rainfall records. SPI comes in Milestone 2.
- Data sources: CHIRPS v3 Final (monthly, 0.05 degree, 60S-60N, 1981-present) and ERA5-Land
  monthly means (0.1 degree grid, 1950-present, reanalysis). Their coverage, units, and
  limitations are returned with every result. No global validation is claimed.
- Missing values are never converted to zero and never partially summed.
- Real data is cached under `data/cache/` (git-ignored) with provenance and SHA-256 hashes.

## Setup (repo root, PowerShell)

```powershell
uv sync --extra dev
copy .env.example .env
uv run pytest
uv run ruff check .
```

## Run the API

```powershell
uv run uvicorn climateadapt.api.main:app --reload
```

Docs: http://127.0.0.1:8000/docs

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness and version |
| `POST /v1/analysis/rainfall-anomaly` | Prototype anomaly from user-supplied totals |
| `POST /v1/analysis/chirps-rainfall-anomaly` | Anomaly computed from CHIRPS v3 Final |

A cold CHIRPS request downloads many ~22 MB files and can take many minutes. Warm the cache
first with the CLI, then call the API.

## Scripts

```powershell
# CHIRPS anomaly (also warms the cache). Use points that are NOT on a multiple of 0.05 degrees.
uv run python scripts/chirps_anomaly.py --lat 30.43 --lon -9.61 --observed-start 2024-01 --window-months 3 --baseline-start-year 2011 --baseline-end-year 2020

# CHIRPS access checks
uv run python scripts/chirps_cli.py probe --year 2024 --month 1
uv run python scripts/chirps_layout_probe.py local "data/cache/chirps_v3/monthly_global/chirps-v3.0.2024.01.tif"

# ERA5-Land (needs CDS credentials, below)
uv run python scripts/era5land_cli.py series --variable total_precipitation --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03
```

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

## Configuration

See `.env.example` (`CLIMATEADAPT_DATA_DIR`, `CLIMATEADAPT_ALLOW_DOWNLOADS`,
`CLIMATEADAPT_HTTP_TIMEOUT_SECONDS`, `CLIMATEADAPT_CHIRPS_BASE_URL`). Set
`CLIMATEADAPT_ALLOW_DOWNLOADS=false` for cache-only, reproducible runs.

## Error behaviour

All errors use `{"detail": [{"loc": [], "msg": "...", "type": "<code>"}]}` with codes:
`outside_coverage` (422), `data_not_available` (404), `missing_data` (422),
`insufficient_baseline` (422), `download_error` (502), `data_integrity_error` (502).
Invalid requests are 422. A zero baseline returns 200 with `status: "undefined"`.