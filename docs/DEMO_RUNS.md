# Demo runs (P14) — real data at four contrasting locations

Pipeline probes, **not validation**. These runs exercise the real CHIRPS and
ERA5-Land clients plus the full agent pipeline at four points chosen to hit
different coverage branches. They say nothing about agronomic correctness and
nothing about locations not listed here. See KI-14.

## Conditions (read before citing any number)

- Date: 2026-10-31. Runner: `scripts/capture_demo_snapshot.py` (full
  `run_scenario_job`: bundle → retrieval → ranking → draft → validate →
  finalize). Captures landed in git-ignored `data/demo_snapshots/`; since P19
  the three audited ones also ship in tracked `demo/snapshots/`.
- LLM: the deterministic no-key provider, always. **Zero model calls, $0.**
  Every report below is the labelled deterministic fallback, never model prose.
- Identical scenario except lat/lon (isolates geography): target 2024-03,
  3-month window, reference 1991–2020, min 30 years, fallback 15 km, all four
  indicators, query "deficit irrigation scheduling", wheat, irrigated.
  Crop/system are held constant as pipeline controls, not as advice — the
  ocean point obviously grows no wheat.
- Corpus: 5 ingested docs (1824 chunks), BM25. Catalog v1 (3 irrigation
  entries). All runs ranked the same two options and excluded the third;
  ranking differences were not the object of study.
- Environment limits (sandbox): direct HTTPS egress to `data.chc.ucsb.edu`
  from GDAL is blocked here (npm registry and CDS are allowed), so CHIRPS
  remote reads fail **in this sandbox only**; the CHIRPS remote path is proven
  outside it ("remote mode: same anomaly digits" in IMPLEMENTATION_STATUS).
  CDS works but is slow here (~minutes per grouped request, kB/s downloads).
  No `TestClient`/browser-server runs were possible (socket block); the UI
  verification for these payloads is the Playwright file:// suite plus
  throwaway render checks (deleted after use).

## Results

### 1. reference-morocco — Souss-Massa, Morocco (30.43, -9.61)

Command: `capture_demo_snapshot.py --key reference-morocco --lat 30.43 --lon -9.61`
(same flags as below). Captured 2026-10-31T22:01:05Z. Trace 5 s, all stages ok
(draft failed → fallback, as designed without a key). Status `partial`.

| Indicator | Status | Values |
|---|---|---|
| chirps_spi | ok (per-point cache, fully warm: 93 month-files) | SPI −0.517, total 76.87 mm, 30 ref years |
| era5_spi | ok (cache) | SPI −0.375, total 59.15 mm, 30 ref years |
| era5_temperature_anomaly | ok (cache) | +2.218 °C, percentile 1.0 |
| era5_soil_moisture_anomaly | ok (cache) | −0.0505 m³/m³, percentile 0.2 |

Observation: the warm-cache path. ERA5-Land used the 15 km land fallback
(requested 30.43, used grid 30.5) and reports it in the entry.

### 2. punjab-india — Punjab, India (30.90, 75.80)

CHIRPS coverage outside Africa. Captured 2026-10-31T22:40:05Z (recapture;
see below). Trace 11 s, all stages ok. Status `partial`.

| Indicator | Status | Values |
|---|---|---|
| chirps_spi | **failed** `download_error` | Sandbox egress block, not a product result (below) |
| era5_spi | ok (**fresh CDS**) | SPI −1.216, total 78.56 mm, 30 ref years |
| era5_temperature_anomaly | ok (**fresh CDS**) | −0.704 °C, percentile 0.3 |
| era5_soil_moisture_anomaly | ok (**fresh CDS**) | −0.0549 m³/m³, percentile 0.133 |

First attempt hit the 900 s agent budget during CDS downloads (bundle stage
took 1461 s at ~kB/s here), skipping retrieval/ranking/draft/validate; the
recapture with `--timeout 3600` ran all stages in 11 s on warm caches. Lesson
for demos: cold CDS locations need a generous timeout or pre-warmed caches.
CHIRPS error (verbatim): `Remote read of .../chirps-v3.0.2024.01.tif failed:
CURL error: Failed to connect to 127.0.0.1 port 56927` (with proxy env) /
`UnicodeDecodeError` in rasterio error handling (direct). Both are this
sandbox's egress policy; the owner can re-run the capture outside it.

### 3. trondelag-norway — Trøndelag, Norway (63.40, 10.40)

North of 60°N. Captured 2026-10-31T22:32:14Z. Trace 356 s (CDS queues),
all stages ok. Status `partial`.

| Indicator | Status | Values |
|---|---|---|
| chirps_spi | **failed** `outside_coverage` | `Point (lat=63.4, lon=10.4) is outside the nominal CHIRPS v3 coverage (latitude -60 to 60 ...). No value is returned.` — the required branch, exact code |
| era5_spi | ok (**fresh CDS**) | SPI −2.121, total 125.71 mm, 30 ref years |
| era5_temperature_anomaly | ok (**fresh CDS**) | +0.874 °C, percentile 0.5 |
| era5_soil_moisture_anomaly | ok (**fresh CDS**) | +0.0191 m³/m³, percentile 0.933 |

Observation: the coverage gate fires before any remote read (fast, no
traffic); ERA5-Land is unaffected by the 60°N CHIRPS limit.

### 4. atlantic-ocean — Atlantic off Morocco (30.43, −15.50)

Ocean / masked point. Captured 2026-10-31T22:36:24Z. Trace 221 s,
all stages ok. Status `partial`.

| Indicator | Status | Values |
|---|---|---|
| chirps_spi | **failed** `internal` | Sandbox egress block (point is inside the CHIRPS bbox, so no coverage gate; the remote read then fails as in Punjab) |
| era5_spi | **failed** `missing_data` | `The target window has no value for: 2024-01, 2024-02, 2024-03. ... If the nearest ERA5-Land grid point is masked (for example sea), retry with land_fallback_max_km.` Grid point null; fallback searched 15 km and found no land |
| era5_temperature_anomaly | **failed** `missing_data` | Same shape as above |
| era5_soil_moisture_anomaly | **failed** `missing_data` | Same shape as above |

Observations: the masked-point path reports honest `missing_data` with a
null grid point — nothing is imputed. Minor wart: the hint says "retry with
land_fallback_max_km" even though the fallback was already enabled (15 km);
the hint should only appear when the fallback was off or narrower. Not fixed
in P14 (cosmetic, out of scope).

## Failure modes seen (for the demo fallback plan)

1. Cold CDS locations take minutes (queues + slow links here) and can exceed
   the 900 s default agent budget → skipped stages + `[total-timeout]`, still
   a labelled partial result. Mitigation: `--timeout 3600`, or warm caches
   ahead of the demo, or present the snapshots.
2. No Baseten key (or any draft failure) → `[provider-auth]` + deterministic
   fallback. This is the expected demo configuration, not an error.
3. CHIRPS remote reads fail in egress-restricted networks with `download_error`
   (or `internal` when the error page itself breaks decoding). The cached
   reference point is unaffected.
4. Ocean/masked points fail ERA5 indicators with `missing_data`, never zeros.

## What was NOT tested

Any location not listed above; any target month/window/reference except
2024-03 / 3-month / 1991–2020; live (downloaded) CHIRPS GeoTIFFs; CDS
behaviour under protection-measure throttling beyond what happened to occur;
model-written drafts (no live LLM call was made in P14).

## Snapshot catalogue

Regenerate any entry with the command in `scripts/capture_demo_snapshot.py`
(changing `--key`/`--label`/coords). Since P19, `reference-morocco`,
`trondelag-norway`, and `atlantic-ocean` ship in tracked `demo/snapshots/`
(see `demo/README.md` for the audit); `punjab-india` stays git-ignored under
`data/demo_snapshots/` because its CHIRPS entry failed on sandbox-blocked
egress (proxy address in the stored error text) — recapture outside the
sandbox to track it.

| Key | Label | Captured (UTC) | Status |
|---|---|---|---|
| reference-morocco | Reference: Souss-Massa, Morocco (30.43, -9.61) | 2026-10-31T22:01:05Z | partial |
| reference-morocco-ai | Reference + Muse Spark accepted (same point) | 2026-11-02 (from run-20261102T202227Z) | complete |
| punjab-india | Punjab, India (30.90, 75.80) | 2026-10-31T22:40:05Z | partial |
| trondelag-norway | Trøndelag, Norway (63.40, 10.40) | 2026-10-31T22:32:14Z | partial |
| atlantic-ocean | Atlantic off Morocco (30.43, -15.50) | 2026-10-31T22:36:24Z | partial |

The four P14 captures are `partial` solely because no LLM key was configured
(deterministic fallback by design); deterministic stages are complete in every
snapshot. `reference-morocco-ai` (P25) is `complete`: the accepted Muse Spark
report from run-20261102T202227Z (14/14 statements validated; first draft
rejected `invalid-json`, repair accepted) with the deterministic bundle/ranking
recomputed offline ($0, no new model call) — see `docs/MUSE_SPARK_EVIDENCE.md`.
