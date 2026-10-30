# DATA_VERIFICATION.md — ERA5-Land units and CDS-client retry options (P02)

Date: 2026-10-30. Author: Muse Code (P02 task). All commands ran from the repo root
on Windows/PowerShell. No secrets are recorded here: CDS credentials were read by cdsapi
from `~/.cdsapirc` (never opened); `.env` was never opened.

## 1. Cached NetCDF inspections (offline)

### 1.1 Soil water layer 1

Command:

```powershell
uv run python scripts/inspect_nc.py "data\cache\era5_land\raw\504d1adaca31d5f7.nc"
```

Result (exit 0): variable `swvl1`, `units` = `m**3 m**-3` (identical `GRIB_units`),
3x3 grid, 3 time steps (2024-01/02/03). Grid point (30.4, -9.6) NaN in all months;
neighbour (30.5, -9.6) = 0.070251 / 0.110382 / 0.112000. File history: GRIB converted
2026-10-27 via cfgrib-0.9.15.1/ecCodes-2.48.2.

Verbatim variable block:

```text
variable 'swvl1': dims=('valid_time', 'latitude', 'longitude') shape=(3, 3, 3) dtype=float32
  attributes: {... 'GRIB_units': 'm**3 m**-3', ... 'units': 'm**3 m**-3', ...
    'GRIB_name': 'Volumetric soil water layer 1', ...}
  share of NaN values overall: 0.444
  time step 2024-01-01:
                -9.70      -9.60      -9.50
     30.50        NaN   0.070251   0.087738
     30.40        NaN        NaN   0.024872
     30.30        NaN   0.044815   0.052002
  time step 2024-02-01:
                -9.70      -9.60      -9.50
     30.50        NaN   0.110382   0.126755
     30.40        NaN        NaN   0.069199
     30.30        NaN   0.077362   0.083588
  time step 2024-03-01:
                -9.70      -9.60      -9.50
     30.50        NaN   0.112000   0.127441
     30.40        NaN        NaN   0.058746
     30.30        NaN   0.078659   0.081039
```

### 1.2 Total precipitation

Command:

```powershell
uv run python scripts/inspect_nc.py "data\cache\era5_land\raw\19dd3da20aa42dbf.nc"
```

Result (exit 0): variable `tp` (`Total precipitation`), `units` = `m` (identical
`GRIB_units`), 3x3 grid, 2024-01/02/03. Same NaN pattern ((30.4, -9.6) and the -9.7
column masked). File history: GRIB converted 2026-10-25 via cfgrib-0.9.15.1/ecCodes-2.48.2.

### 1.3 2 m temperature

Command:

```powershell
uv run python scripts/inspect_nc.py "data\cache\era5_land\raw\6fe2b9a95886f907.nc"
```

Result (exit 0): variable `t2m` (`2 metre temperature`), `units` = `K` (identical
`GRIB_units`), 3x3 grid, 2024-01/02/03. Same NaN pattern. File history: GRIB converted
2026-10-27 via cfgrib-0.9.15.1/ecCodes-2.48.2. This upgrades the handoff's
"units must have been K" (implied by a passing run) to directly observed.

## 2. Live CDS requests (2 of max 4)

Both used the reference point (lat 30.43, lon -9.61) with `--land-fallback-km 15`
and a single month (2024-01). Each log opened with the CDS banner
"**Data Stores Service protection measures** affecting data downloads and account
access" (2026-10-06 notice) — no throttling was observed; both requests completed.

### Live request 1 — soil water layer 2

Command:

```powershell
uv run python scripts/era5land_cli.py series --variable volumetric_soil_water_layer_2 --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-01 --land-fallback-km 15
```

Result (exit 0, ~15 s queue+download): request ID `4049589c-...-e96e2b0291f1`,
status accepted -> successful, 24.6 kB NetCDF (not zip). Series value for 2024-01:
0.1384 m3/m3 with LAND FALLBACK USED ((30.4, -9.6) masked, took (30.5, -9.6), 7.8 km).
Raw file: `data\cache\era5_land\raw\49ed8165fe0f7ab7.nc` (25,190 bytes,
sha256 `70ec9a332a79cab0...`).

Follow-up offline inspection of that file: variable `swvl2`
(`Volumetric soil water layer 2`), `units` = `m**3 m**-3` (identical `GRIB_units`),
1x3x3. (30.5, -9.6) for 2024-01-01 = 0.138428, matching the series value 0.1384.
File history: GRIB converted 2026-10-30 via cfgrib-0.9.15.1/ecCodes-2.48.2.

### Live request 2 — soil water layer 3

Command:

```powershell
uv run python scripts/era5land_cli.py series --variable volumetric_soil_water_layer_3 --lat 30.43 --lon -9.61 --start 2024-01 --end 2024-01 --land-fallback-km 15
```

Result (exit 0, ~35 s queue+download): request ID `7594acc4-...-0d607af92be8`,
status accepted -> running -> successful, 24.6 kB NetCDF (not zip). Series value for
2024-01: 0.1545 m3/m3 with LAND FALLBACK USED (same points as above).
Raw file: `data\cache\era5_land\raw\6847b4ab8f794ca0.nc` (25,190 bytes,
sha256 `20a8eb7c59f3915b...`).

Follow-up offline inspection of that file: variable `swvl3`
(`Volumetric soil water layer 3`), `units` = `m**3 m**-3` (identical `GRIB_units`).

No further live requests were made (2 used of the 4-request budget).

## 3. Installed cdsapi retry options (offline)

Command:

```powershell
uv run python -c "import inspect, cdsapi; from importlib.metadata import version; print('cdsapi', version('cdsapi')); print(inspect.signature(cdsapi.Client.__init__))"
```

Result (exit 0), verbatim except the session-object address trimmed:

```text
cdsapi 0.7.7
(self, url=None, key=None, quiet=False, debug=False, verify=None, timeout=60,
progress=True, full_stack=False, delete=True, retry_max=500, sleep_max=120,
wait_until_complete=True, info_callback=None, warning_callback=None,
error_callback=None, debug_callback=None, metadata=None, forget=False,
session=<requests.sessions.Session object>)
```

All three app bounds exist as explicit keywords: `timeout=60`, `retry_max=500`,
`sleep_max=120`. Therefore `supported_options` in `data/cds_client.py` classifies them
as supported and they ARE passed (app defaults: retry_max=5, sleep_max=60 s,
timeout=60 s — far below cdsapi's own defaults). A new offline test,
`test_installed_cdsapi_exposes_all_retry_options`, pins this against future cdsapi
upgrades.

## 4. Conclusions and code changes

- `total_precipitation` file units `{"m"}` and `2m_temperature` file units `{"K"}` match
  observation exactly — no change needed.
- `SOIL_WATER_UNITS` was tightened from four spellings to exactly `{"m**3 m**-3"}`,
  the only spelling observed for all three layers (one cached file + two live
  responses). Unobserved spellings now raise `DataIntegrityError` with the actual
  string, so a future spelling change fails loudly and can be added deliberately.
  Tests updated: observed spelling accepted; `m3 m-3`, `m^3 m^-3`, `m3/m3` rejected.
- KI-05 resolved; KI-08 signature half resolved (see `docs/handoff/KNOWN_ISSUES.md`).
- Still open: live retry behavior under a real failure (deliberately not attempted —
  it would need a failing request and the service carries throttling notices);
  land-sea mask explanation vs ERA5-Land documentation (KI-10; the NaN pattern at
  (30.4, -9.6) was corroborated again by both live responses); CDS terms review is an
  owner action (KI-09).
