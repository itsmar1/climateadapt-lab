# ClimateAdapt Lab

Evidence-grounded AI agent for agricultural drought adaptation (Meta Global Developer AI
Hackathon project). **Status: Milestone 1** - tested CHIRPS v3 and ERA5-Land point connectors
and a CHIRPS-based rainfall-anomaly endpoint. SPI and further indicators are Milestone 2.

## Scientific scope and limitations

- Implemented indicator: a simple precipitation **percentage anomaly**
  `((observed_total - baseline_mean) / baseline_mean) * 100`. It is a prototype, **not** a
  calibrated drought index, and must not be used alone to classify drought severity. It is
  mean-based and can mislead on skewed rainfall records.
- Data sources: CHIRPS v3 Final (monthly, 0.05 degree, 60S-60N, 1981-present) and ERA5-Land
  monthly means (0.1 degree grid, 1950-present, reanalysis). Coverage, units, and
  limitations are returned with every result. No global validation is claimed.
- **Products can disagree strongly.** In one real test the two precipitation products agreed on
  the 3-month total only to within the same order of magnitude and disagreed month by month.
  Use `scripts/compare_chirps_era5.py` and treat disagreement as uncertainty.
- Missing values are never converted to zero and never partially summed.
- ERA5-Land has no value at masked (for example sea) grid points. Default: months are reported
  as missing. Opt-in `--land-fallback-km` uses the nearest valid neighbour and always reports
  the substitution.
- A point exactly on a CHIRPS cell edge or corner is flagged, because the cell used is
  arbitrary. Use points that are not multiples of 0.05 degrees.

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

## CHIRPS access modes

`CLIMATEADAPT_CHIRPS_ACCESS` selects how CHIRPS is read:

- `remote` (default): one pixel per month via HTTP range requests. A real 33-month pipeline run
  took about 30 s cold. Provenance records the server's size, ETag, and Last-Modified (no
  file hash, because the file is never downloaded).
- `download`: whole ~22 MB monthly files, cached with a SHA-256 provenance sidecar.
  Slower (about 35 s per file on the verified connection) but archival-grade.

`CLIMATEADAPT_PREFETCH_WORKERS` (1-8, default 4) sets parallel remote reads. Set
`CLIMATEADAPT_ALLOW_DOWNLOADS=false` for cache-only, reproducible runs.

## Scripts

```powershell
# CHIRPS anomaly (also warms the cache)
uv run python scripts/chirps_anomaly.py --lat 30.43 --lon -9.61 --observed-start 2024-01 --window-months 3 --baseline-start-year 2011 --baseline-end-year 2020

# CHIRPS access check and point series
uv run python scripts/chirps_cli.py probe --year 2024 --month 1
uv run python scripts/chirps_cli.py series --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03

# ERA5-Land (needs CDS credentials, below); add --land-fallback-km 15 if the point is masked
uv run python scripts/era5land_cli.py series --variable total_precipitation --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03

# Side-by-side product comparison
uv run python scripts/compare_chirps_era5.py --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-03 --land-fallback-km 15

# Inspect a downloaded ERA5-Land NetCDF (no network)
uv run python scripts/inspect_nc.py "data\cache\era5_land\raw\<file>.nc"
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

See `.env.example`. Real data is cached under `data/cache/` (git-ignored).

## Error behaviour

All errors use `{"detail": [{"loc": [], "msg": "...", "type": "<code>"}]}` with codes:
`outside_coverage` (422), `data_not_available` (404), `missing_data` (422),
`insufficient_baseline` (422), `download_error` (502), `data_integrity_error` (502).
Invalid requests are 422. A zero baseline returns 200 with `status: "undefined"`.