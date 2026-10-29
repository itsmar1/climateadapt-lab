# AGENTS.md — ClimateAdapt Lab

Instructions for any coding agent working in this repository. Keep this file short; details live in `docs/handoff/`.

## 1. What this project is

ClimateAdapt Lab is an evidence-grounded decision-support platform for agricultural drought adaptation (hackathon project). Users pick a location, season and crop; the system computes environmental indicators, retrieves cited scientific evidence, filters and ranks adaptation options with deterministic rules, and an LLM agent turns those results into a structured, traceable report.

**Core principle: deterministic Python computes and enforces; the LLM only coordinates tools and explains.** The LLM never produces an authoritative number, never overrides a hard constraint, and never invents a citation.

Scope is **global-first**: architecture must not hard-code one country. Never claim global validation that has not been performed; every data source must state its real coverage.

## 2. Read these first

1. `docs/handoff/IMPLEMENTATION_STATUS.md` — what exists and how well it is verified.
2. `docs/handoff/KNOWN_ISSUES.md` — open problems.
3. `docs/handoff/PROJECT_CONTEXT.md` — vision, model access, overridden decisions.
4. `docs/handoff/IMPLEMENTATION_ROADMAP.md` and `MUSE_CODE_TASK_PROMPTS.md` — the plan and per-task prompts.

Those documents were written from conversation history, not from the repository. **The repository is authoritative. If it disagrees with a handoff document, trust the repository, say so, and fix the document.**

## 3. Status vocabulary (use it in every report and doc)

- **CONFIRMED** — you ran it in this session and recorded the output, or a log in the repo/docs shows it.
- **REPORTED** — someone said it works; you have no output. Never present as fact.
- **UNVERIFIED** — written but never run, or assumed. Includes anything about external APIs you have not called.

Never upgrade a status without running something and quoting the result. Never write "tests pass" unless you ran the suite and report the final counts line.

## 4. Stack and layout

- Backend: Python 3.11, `uv`, FastAPI + Pydantic v2, `src/climateadapt/` (src layout). Tests in `tests/`. Windows/PowerShell is the owner's environment — avoid bash-only commands in docs.
- Frontend: **React + Vite** in `frontend/` (not yet created). **Do not introduce Streamlit** (the original blueprint mentioned it; it is superseded).
- Retrieval: BM25 + Reciprocal Rank Fusion implemented; dense retrieval (multilingual E5 + Qdrant) planned.
- Packages: `data/` connectors, `indicators/` pure calculations, `pipelines/` connector+indicator workflows, `rag/` corpus/retrieval, `api/` FastAPI, `scripts/` developer CLIs. Layers import downward only (indicators must not import FastAPI or network code).

## 5. Commands (PowerShell, repo root)

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run uvicorn climateadapt.api.main:app --reload
```

The full suite is slow (~5–8 min, many synthetic rasters). Run targeted tests while iterating, then the full suite before reporting.

## 6. Coding and testing conventions

- `from __future__ import annotations`; type hints on public functions; ruff (`E,F,I,B,UP`), line length 100. Do not put calls in argument defaults (B008) — use module constants.
- Pydantic models: `extra="forbid"`; strict numeric types on API input; no NaN/Inf accepted.
- **Tests never use the network or credentials.** Use synthetic data and the existing fakes (`httpx.MockTransport`, `FakeDownloader`, fixtures in `tests/conftest.py`, `tests/era5_helpers.py`, `tests/rag_helpers.py`). Real-data runs happen only in `scripts/` or explicitly gated smoke tests.
- Every behavior change ships with tests, including failure and edge cases. Assert on specific values/messages, not just "no exception".
- API errors use one shape: `{"detail": [{"loc": [...], "msg": "...", "type": "<code>"}]}` with stable codes (`outside_coverage` 422, `data_not_available` 404, `missing_data` 422, `insufficient_baseline` 422, `insufficient_reference` 422, `download_error` 502, `data_integrity_error` 502). Add codes deliberately and document them.
- Validate everything **before** any network access (fail fast).

## 7. Scientific correctness and provenance (non-negotiable)

1. Missing is never zero; never sum partial windows; exclude and report incomplete reference years, never impute.
2. Verify units from file metadata before converting; reject unexpected units.
3. One grid point per series; ERA5-Land land-fallback is opt-in and must be reported prominently.
4. Every analytical result carries provenance (source, URL/request, retrieval time, hash or ETag where available), citation, licence note and limitations.
5. Document reference periods, units, missing-value handling and assumptions in code and in responses.
6. No single composite "drought severity" score and no severity labels from one indicator. SPI category labels stay out until their definitions are verified from a primary source.
7. The simple percentage anomaly is a prototype, not a drought index.
8. Distinguish synthetic data, user-supplied data and real observations everywhere.
9. Do not fabricate measurements, citations, dataset coverage, intervention benefits, costs or model performance. Unknown stays explicitly unknown.
10. Hard constraints live in deterministic code; an LLM output is validated against retrieved sources and schemas before it reaches a user.

## 8. Data, credentials and external APIs

- Never commit or print secrets: `.env`, `%USERPROFILE%\.cdsapirc`, API keys, tokens. Do not put secrets in frontend code, logs, prompts, test fixtures or docs. `data/` is git-ignored; keep it that way.
- Muse Code's own authentication and the **application's inference-provider credentials are separate**. Never reuse one for the other and never hard-code either.
- Application LLM access: Baseten, model `meta-models/muse-spark-open-1026`, with credits and rate limits. **Do not assume any other model ID or provider endpoint exists.** Endpoint, auth method, tool-calling and structured-output support are UNVERIFIED until checked against current Baseten documentation and a gated smoke call. Isolate all model calls behind a provider adapter; tests use a fake provider.
- Before using any external API/SDK, read its current official documentation and record the source. Do not invent endpoints, parameters or options.
- Copernicus CDS requires an account, dataset terms acceptance and `cdsapi`; calls queue for seconds to minutes and the service has issued protection-measure notices. Keep requests few and grouped, honour caches, and keep `CLIMATEADAPT_ALLOW_DOWNLOADS=false` available for reproducible offline runs.
- Corpus documents have mixed licences (some NC/ND). Never commit PDFs or extracted text; only `corpus/manifest.json` and `corpus/eval/` are versioned. Keep quotes short and attributed.
- Live calls consume the owner's credits/rate limits: keep smoke tests tiny, gated by an explicit environment variable, and report what you spent.

## 9. Incremental implementation rules

- One task = one reviewable change. Inspect before editing; read the existing module and its tests first.
- **Do not rewrite, rename or "modernize" working components** to suit your preferences. Fix verified problems minimally.
- Do not start the next milestone before the current one is verified. Stop and report if blocked; do not guess.
- Run `uv run pytest` and `uv run ruff check .` before declaring done and paste the final counts/output. If you cannot run something, say so.
- No destructive git operations (no force-push, history rewrite, mass deletion). Check `git status` first.
- Update the relevant handoff docs (status, issues, README) in the same change.

## 10. Frontend (React + Vite) and API requirements

- `frontend/`, Vite + React, TypeScript strict unless the owner decides otherwise. Talk to FastAPI through a typed client; no secrets in the bundle (only public `VITE_*` values).
- Surface for every result: data source, coverage, reference period, units, limitations, provenance and citations. Show API error `type` codes as clear, specific messages. Never display an LLM-written number as authoritative.
- Long-running analyses (cold CHIRPS reads, CDS requests) must not block an HTTP call indefinitely: use cache warming or job polling with progress and timeouts.
- FastAPI: versioned `/v1` routes, OpenAPI as the frontend contract, CORS configured explicitly for the dev origin, input validated by Pydantic.

## 11. Definition of done

Code + tests + docs updated; full test suite and ruff run with **actual** results reported; limitations and remaining risks listed; every claim labelled CONFIRMED / REPORTED / UNVERIFIED; no secrets or corpus text staged for commit.

## 12. Report format for every task

1. What changed (files). 2. Commands run and their actual output (final pytest/ruff lines). 3. New or changed behavior, with evidence. 4. What remains UNVERIFIED. 5. New issues found. 6. Docs updated.
