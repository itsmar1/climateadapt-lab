# Tracked demo snapshots

Stored real-data runs served by `GET /v1/demo/*` when `CLIMATEADAPT_DEMO_MODE=true`.
These files are **versioned on purpose**: a fresh clone serves them with zero keys,
zero credentials, and no corpus. The API serves them verbatim; clients must label
them "cached real-data snapshot" with the capture timestamp, never a live result.

## Provenance (P19 audit 2026-11-01, CONFIRMED; P25 addition 2026-11-02)

- Captured 2026-10-31 with `scripts/capture_demo_snapshot.py` (full
  `run_scenario_job`, deterministic no-key provider: zero model calls, $0).
  Full conditions in `docs/DEMO_RUNS.md`.
- `reference-morocco-ai` (P25): built from the saved accepted run
  `data/agent_runs/run-20261102T202227Z.json` with
  `capture_demo_snapshot.py --from-run` ($0, no new model call;
  deterministic bundle/ranking recomputed offline and the saved report
  re-validated; raw draft/repair text stripped). Same audit passed;
  per-stage trace, token usage, and the repair verdict are preserved.
  Evidence page: `docs/MUSE_SPARK_EVIDENCE.md`.
- Every file passed the pre-commit audit: evidence items carry citation
  metadata only (no corpus passage text anywhere); every computed indicator
  carries CHIRPS / ERA5-Land `citation`, `license_note`, `data_source`, `doi`;
  no local paths, secrets, or user identifiers.
- `punjab-india` (kept only under git-ignored `data/demo_snapshots/`) was
  **excluded**: its CHIRPS entry failed on this sandbox's blocked egress and
  the stored error text names a sandbox proxy address. Recapture it outside
  the sandbox to add it here.

## Licence notes

Snapshot *values* are measurements/attribution from public sources, served with
their citations: CHIRPS v3 Final (public domain / CC BY 4.0 per CHC; Funk et
al. 2026) and ERA5-Land monthly means (Copernicus licence; Muñoz Sabater
2019; acknowledge "Copernicus Climate Change Service Information"). Evidence
entries are short attributed citations (title/authors/pages/URL/licence), not
document text — corpus PDFs and extracted text are never committed (AGENTS.md
§8). Do not add snapshots containing passage text, secrets, or local paths.
