# Demo script — ClimateAdapt Lab

A reproducible 10-minute walk-through. Two tracks: **live run** (needs the
backend + caches) and **snapshots** (needs only demo mode; works offline and
under rate limits). Real outputs for every step live in `docs/DEMO_RUNS.md`.

## Prerequisites

```powershell
uv sync --extra dev
```

Backend (repo root):

```powershell
# Live track:
uv run uvicorn climateadapt.api.main:app --reload
# Snapshots track (same server, demo endpoints on):
$env:CLIMATEADAPT_DEMO_MODE = 'true'
uv run uvicorn climateadapt.api.main:app --reload
```

Frontend (needs Node 20.19+; this machine keeps a portable Node under
untracked `node-tmp/` because the system Node is v16):

```powershell
cd frontend
npm install
npm run dev     # strict http://localhost:5173 (matches API CORS default)
```

Open http://localhost:5173 in a browser.

## Track A — live run (reference point, warm caches)

1. The form opens with the reference scenario prefilled: 30.43, −9.61,
   target 2024-03, 3-month window, reference 1991–2020, wheat, irrigated.
   Press **Run analysis**.
2. **Expected:** "Analysis running" for ~6 s (warm) with 2 s polling, then
   the Results page: four indicator cards (CHIRPS SPI −0.517, ERA5 SPI −0.375,
   temperature +2.22 °C, soil −0.0505 m³/m³), the deterministic ranking
   (Deficit irrigation + Irrigation scheduling at 0.750, one exclusion with
   reasons, Unknown badges everywhere benefit/cost/risk is unstated), and the
   cited report with evidence links, platform-value chips, and the
   always-visible limitations.
3. Without a Baseten key (the expected demo configuration) the report shows
   the **Deterministic fallback** banner and a `[provider-auth]` problem.
   Say so out loud: no model ran; every number is computed.
4. Open **History**: the run is listed with its status badge; failed runs
   expand to show problems. Press **Export report (Markdown)** to download
   the cited report.

## Track B — cached snapshots (offline-proof)

1. Click **Demo** (or open `#/demo`). Four stored real-data runs are listed
   with capture timestamps: Morocco (4/4 ok), Punjab (ERA5 ok),
   Norway (CHIRPS `outside_coverage`, ERA5 ok), Atlantic (ERA5 `missing_data`
   — the masked-point path).
2. Open each. **Expected:** the identical results UI plus the amber
   **Cached real-data snapshot** banner ("Stored results, not a live run").
3. If the list shows "Demo mode is disabled", the server was started without
   `CLIMATEADAPT_DEMO_MODE=true` — restart it with the flag. Snapshots live
   in git-ignored `data/demo_snapshots/`; regenerate with
   `scripts/capture_demo_snapshot.py` (see its `--help`).

## Fallback plan (say what is happening, then switch tracks)

| Failure | What the audience sees | Presenter action |
|---|---|---|
| No Baseten key / model error | Fallback banner + `[provider-auth]` problem | Expected: "deterministic mode, no AI narrative" |
| Cold CDS location, minutes pass | Progress polls, possible `[total-timeout]` partial | Switch to Track B; the Punjab/Norway snapshots already show fresh-CDS values |
| CHIRPS remote reads fail | `download_error` entry, ERA5 cards still render | "CHIRPS needs its tile host; ERA5-Land carries the demo" |
| Backend down entirely | "Backend could not be reached" | Restart `uvicorn`; if it stays down, narrate the snapshot JSONs in `data/demo_snapshots/` directly |

## Do not claim

- That any location outside `docs/DEMO_RUNS.md` was tested.
- That SPI values or anomalies were validated against ground truth.
- That a snapshot is a live result (it is bannered; repeat it once).
- Any severity label, composite score, cost, or benefit the sources do not
  state — the UI never shows them; neither should the presenter.
