# Demo script — 3-minute video (P21, UI updated P26)

180 seconds, four timed beats mapped to the provisional rubric
(`PROJECT_CONTEXT.md` §3 — the official rubric is still unknown, KI-32).
Recording setup: captured snapshots plus **one warmed live run**, so the
video never waits on a cold download. All numbers below are real outputs
recorded in `docs/DEMO_RUNS.md`.

## Pre-warm (do once, ~10 minutes before recording)

Goal: the reference live run finishes in seconds on camera. Cold CDS legs
take minutes and have exceeded the 900 s agent budget on slow links — never
record cold.

```powershell
# Terminal 1 — backend with snapshots on (repo root)
uv sync --extra dev
$env:CLIMATEADAPT_DEMO_MODE = 'true'
uv run uvicorn climateadapt.api.main:app --reload   # http://127.0.0.1:8000/docs

# Terminal 2 — frontend
cd frontend
npm install        # first time only (needs Node 20.19+)
npm run dev        # http://localhost:5173
```

```powershell
# Terminal 3 — fire the reference scenario once to warm every cache
$body = @{
  latitude = 30.43; longitude = -9.61; target_end_month = "2024-03"
  timescale_months = 3; reference_start_year = 1991; reference_end_year = 2020
  min_reference_years = 30; land_fallback_max_km = 15.0
  indicators = @("chirps_spi", "era5_spi", "era5_temperature_anomaly",
    "era5_soil_moisture_anomaly")
  query = "deficit irrigation scheduling"; top_k = 5; exclude_reference = $true
  crop = "wheat"; has_water_source = $true; has_irrigation_equipment = $true
  production_system = "irrigated"; season = "2024-03"
} | ConvertTo-Json
$created = Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/scenarios `
  -Method Post -Body $body -ContentType "application/json"
do {
  Start-Sleep -Seconds 5
  $d = Invoke-RestMethod "http://127.0.0.1:8000/v1/scenarios/$($created.scenario_id)"
  $d.status
} until ($d.status -in @('complete', 'partial', 'failed'))
```

Checklist before pressing record: `$d.status` reached `partial` (no-key
fallback — the expected demo configuration, $0 spent); `#/demo` lists four
snapshots; a second run of the same scenario returns in seconds; screen at
1280×800 or wider so the map and strip fit one frame.

## Beat 1 — Impact, 0:00–0:20

SHOW: the Overview landing (purpose + coverage map with run markers).
SAY: "Agronomists and planners facing drought must choose between adaptation
options — deficit irrigation, scheduling, water harvesting — with scattered
evidence. ClimateAdapt Lab turns one location and season into computed
indicators, cited science, and ranked options with explicit unknowns."

## Beat 2 — Meta tooling, 0:20–0:50

SHOW: results strip with the "Platform fallback report" badge; open "Why this
is the platform fallback".
SAY: "Meta's Muse Spark model drafts the report through Baseten — tool-calling
verified live. But the model never gets the last word: every draft is
validated against the schema, the citations, and the computed numbers. This
draft was rejected, so you see the labelled deterministic fallback instead —
no AI narrative, no invented values."

## Beat 3 — Technical depth, 0:50–1:20

SHOW: one indicator card (expand Limitations & provenance); the Location map
with both markers; citation chips in the report.
SAY: "Every value carries provenance, units, reference period, and
limitations. The CHIRPS band is shaded because coverage is honest, not
assumed. ERA5-Land fell back to a neighbouring grid cell, and the map shows
both points with the distance. No severity labels anywhere — the tests forbid
them. Over 800 backend checks green, 118 frontend unit tests, 9
end-to-end — green, including a console-error guard."

## Beat 4 — Live demo, 1:20–3:00

- 1:20 — On **New analysis**, click the **Morocco (reference)** preset,
  jump to step 4, press **Run analysis**. The warmed run lands in seconds.
- 1:40 — Read the sticky strip: location, window, 1991–2020 reference, status
  badges. Open the Indicators tab; point at CHIRPS SPI −0.517 vs ERA5 SPI
  −0.375 — "two products, both shown, disagreement is uncertainty."
- 2:05 — Evidence & options tab: two options tied at 0.750 with score breakdowns,
  one exclusion with reasons, Unknown badges where sources are silent.
- 2:20 — Report tab: evidence chips E1…En, verbatim citations with pages and
  licence notes, always-visible limitations. Press **Export report
  (Markdown)**.
- 2:35 — **Demo** page: open Norway — CHIRPS `outside_coverage`, ERA5 fine;
  open Atlantic — ERA5 `missing_data` on a masked point, never zeros.
- 2:55 — Close: "Computed where computable, cited where stated, honest
  everywhere else."

## Fallback plan (if anything fails mid-take)

| Failure | Presenter action |
|---|---|
| Live run hangs (cold cache) | Cut; show the Morocco snapshot — identical UI plus the amber banner |
| Backend down | Restart `uvicorn`; if it stays down, narrate `demo/snapshots/*.json` |
| No network for map tiles | Markers and shading still render; say tiles need connectivity |
| Draft accepted with a key | Only if pre-tested; otherwise record keyless (fallback is the design) |

## Do not claim

- Any location outside `docs/DEMO_RUNS.md` was tested.
- SPI values or anomalies were validated against ground truth.
- A snapshot is a live result (it is bannered; repeat it once).
- Any severity label, composite score, cost, or benefit the sources do not
  state — the UI never shows them; neither should the presenter.
- That Docker/CI are verified: backend image + `/health` are owner-REPORTED;
  frontend image, compose serving, and CI's first run are UNVERIFIED.
