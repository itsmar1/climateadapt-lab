# Submission Checklist (P-final, 2026-11-01)

## 1. What is implemented

- Environmental evidence: CHIRPS v3 + ERA5-Land point connectors with caching,
  provenance, coverage checks; percentage anomaly, SPI (WMO-No. 1090 method),
  temperature and soil-moisture window anomalies; SPI diagnostics and
  cross-product comparison scripts.
- Full v1 API: sync CHIRPS endpoints, 202+poll ERA5/bundle jobs, scenario CRUD
  with SQLite persistence, demo mode; one typed error contract.
- Scientific RAG: 8-source manifest, PDF fetch/ingest, page-aware chunking with
  provenance verification, BM25 + RRF, dense E5 + Qdrant hybrid, citations,
  evaluation harness (5 of 8 documents ingested).
- Recommendations: versioned catalog (v1, irrigation, 3 entries), deterministic
  hard constraints, transparent ranking, `validate_catalog.py`.
- LLM + agent: Baseten provider adapter, versioned report schema, client-side
  validator, deterministic fallback, fixed 7-stage pipeline, gated live scripts
  (endpoint/auth/tool-calling verified live 2026-10-30).
- React + Vite frontend: scenario form, job progress, indicator cards, cited
  report, ranking panel, history, Markdown export, demo page (79/79 Vitest).
- Reproducibility: demo snapshots, Playwright e2e, Dockerfiles + compose stack,
  CI workflow (build/run UNVERIFIED — see §4).
- Vision baseline (isolated from recommendations): classical crop/non-crop
  models on CropHarvest v14, MLflow-tracked, evaluated on 543k held-out rows
  (`docs/VISION_BASELINE.md`).

## 2. What is NOT implemented

- RAG API routes (retrieval exists without HTTP exposure).
- API authentication and rate limiting — do not expose beyond localhost.
- MLOps extras by explicit core-only decision: Optuna, Airflow, PostgreSQL,
  Prometheus, Evidently, Grafana; MLflow runs for the vision baseline only.
- Neural vision model + Optuna (deferred; classical baseline delivered).
- 3 corpus manual PDFs; page-level gold annotations; owner review of RAG labels.
- No model draft has ever been accepted — every live run served the fallback
  (KI-35: prompt must state the registry vocabulary first).

## 3. Known limitations (must accompany any demo)

- Single-point analyses; real runs at 4 locations are coverage probes, not
  validation. No global validation is claimed.
- Products can disagree (CHIRPS vs ERA5-Land) — disagreement is uncertainty.
- Percentage anomaly is a prototype, not a drought index; no severity labels
  anywhere; SPI gamma fit has no goodness-of-fit test.
- Vision metrics describe crop/non-crop classification only — never drought
  damage or intervention effectiveness.
- Full list: README "Known limitations" + `docs/handoff/KNOWN_ISSUES.md`.

## 4. How to run the demo

```powershell
uv sync --extra dev            # on a networked machine; see §6 first
copy .env.example .env
uv run uvicorn climateadapt.api.main:app --reload   # http://127.0.0.1:8000/docs
cd frontend; copy .env.example .env; npm install; npm run dev
```

Offline/rate-limited path: `CLIMATEADAPT_DEMO_MODE=true` serves cached
real-data snapshots (`GET /v1/demo/snapshots`); frontend Demo page (`#/demo`).
Walk-through + fallback plan: `docs/DEMO_SCRIPT.md`; real results at four
locations: `docs/DEMO_RUNS.md`. Docker path (`docker compose up --build`) is
authored but its build/run is UNVERIFIED — confirm before demoing from it.

## 5. How model access is configured

1. Get a Baseten API key (Baseten account); no other provider exists.
2. Put it ONLY in the shell or untracked `.env`:
   `CLIMATEADAPT_BASETEN_API_KEY` (or `BASETEN_API_KEY`). Never commit it.
3. Tiny gated check: `$env:CLIMATEADAPT_RUN_LIVE_LLM = "1";
   uv run python scripts/llm_smoke.py` (≈$0.002 in 2026-10-30).
4. Without a key or flag, the app serves the deterministic fallback and spends
   nothing. Rate/context limits + credit balance are UNVERIFIED — confirm with
   the owner before bigger runs. Details: `docs/LLM_PROVIDER_NOTES.md`.

## 6. Pre-share safety checklist

- [ ] `git status` shows no `.env`, no `data/`, no corpus PDFs/text, no run
      debris (P-final state 2026-11-01: clean — only intended doc/config edits
      plus `docs/FINAL_VERIFICATION.md` and this file).
- [ ] Stage `.env.docker.example` (placeholder-only, un-ignored in P-final;
      verify again with `git diff --cached` that it holds no key).
- [ ] Confirm `.gitignore` still covers `.env`, `data/`, `corpus/**/*.pdf`,
      `corpus/**/*.txt`, `corpus/raw/` (`git check-ignore data .env`).
- [ ] Do not ship `data/` (caches, corpus text, sqlite, snapshots),
      `node-tmp/` (portable toolchain), or `.venv/` — all git-ignored.
- [ ] Corpus redistribution needs licence verification on landing pages first
      (KI-23: mixed licences, some NC/ND). Quote briefly, attribute always.
- [ ] On a networked machine: add the `vision` extra, `uv lock`, re-run the
      full suite unsandboxed, `docker compose up --build`, and push CI once —
      then update `docs/FINAL_VERIFICATION.md` §9.
