# Known Issues

Handoff date: 2026-10-28. Sources: owner's pasted logs and Claude's delivered code (no repository access). Severity: **High** = blocks verified baseline, scientific honesty or the demo; **Medium** = degrades quality/credibility; **Low** = polish. "Prompt" refers to `MUSE_CODE_TASK_PROMPTS.md`. Always re-check each issue against the real repository first (P00).

---

## A. Verification baseline

### KI-01 — Four fixes not verified; suite not known green (High) — ✅ RESOLVED 2026-10-30
- **Evidence:** Last log: 536 collected, 534 passed, 2 failed; ruff reports 2 × B008 (`rag/chunking.py` ~l.61, `rag/ingest.py` ~l.108). Claude proposed four fixes afterwards; no log shows them applied or passing.
- **Impact:** No verified baseline; any later regression is undetectable.
- **Depends on:** nothing.
- **Resolution (P00 → P01):** run suite and ruff; apply only fixes that are still needed: `DEFAULT_CHUNKING_PARAMS = ChunkingParams()` constant used in `chunk_document` and `ingest_document` signatures (and import); in `tests/test_rag_text_chunking.py` change the tamper test to edit a word *inside* the chunk (`pages[0].text.replace("w0030", "w9999")`) and change the prose repeat in the number-heavy test from `* 25` to `* 20`. Report actual final counts.
- **Audit evidence (P00, 2026-10-30; CONFIRMED):** all four fixes were already present — `DEFAULT_CHUNKING_PARAMS` in `src/climateadapt/rag/chunking.py:37,64` and `src/climateadapt/rag/ingest.py:19,108`; in-chunk tamper edit in `tests/test_rag_text_chunking.py:62`; `* 20` in `tests/test_rag_text_chunking.py:82` (AUDIT_REPORT §7). Full suite: **536 passed, 1 warning in 576.54s (0:09:36)**; `ruff check .`: **All checks passed!** No fixes were needed; P01-as-written has nothing to fix.

### KI-02 — Local repository may differ from conversation code (High until audited) — ✅ RETIRED 2026-10-30
- **Evidence:** Owner fixed many ruff findings by hand (8, 3, 26 errors in different batches), edited `tests/test_chirps.py` (regex changed to `"not be published yet"`), and applied multi-step insert/replace patches (e.g., `era5_land.py`, `test_era5_land.py`).
- **Impact:** Handoff docs and prompts may name wrong lines/paths; patches may have been applied differently.
- **Resolution (P00):** treat the repo as truth; produce a file-by-file reconciliation against `IMPLEMENTATION_STATUS.md` §2.
- **Audit evidence (P00, 2026-10-30; CONFIRMED):** reconciliation done (AUDIT_REPORT §2.3) — all 41 `src`, 31 `tests`, 13 `scripts`, corpus and doc paths present, no renames, no extra source files. The repo matches the conversation code. Retired by the audit; the repository remains authoritative for any future discrepancy.

### KI-03 — Slow test suite (Low/Medium) — still open
- **Evidence:** 7 min 44 s (464 s); earlier 4–5 min. Dominated by creating synthetic rasters in SPI/pipeline tests. **P00 audit 2026-10-30 (CONFIRMED): suite now takes 9 min 36 s (576.54 s) and is growing.**
- **Impact:** Slows every Muse Code iteration.
- **Resolution:** reuse a session-scoped synthetic raster set or smaller grids; optionally try `uv run --with pytest-xdist pytest -n auto` (UNVERIFIED on this machine). Do not weaken assertions.

### KI-04 — Starlette/httpx deprecation warning (Low) — still open
- **Evidence:** `StarletteDeprecationWarning ... install httpx2 instead` on every run. **P00 audit 2026-10-30 (CONFIRMED): warning observed verbatim in the green 536-passed run (the suite's single warning); cause still uninvestigated, harmless but noisy.**
- **Resolution:** investigate versions/pins; if no clean fix, leave and document. Do not silence blindly.

---

## B. Environmental data and indicators

### KI-05 — Exact swvl1 `units` string unknown (Medium) — ✅ RESOLVED 2026-10-30
- **Evidence:** `volumetric_soil_water_layer_1` ran successfully (values 0.0703/0.1104/0.1120 m³/m³) so the unit spelling is one of four accepted strings (`m**3 m**-3`, `m3 m-3`, `m^3 m^-3`, `m3/m3`); `scripts/inspect_nc.py` was never run on `data\cache\era5_land\raw\504d1adaca31d5f7.nc`. For `tp`, `inspect_nc` output showed units `m` (CONFIRMED). `t2m` accepted with units `K` (implied by passing run).
- **Impact:** If the real string differs from the accepted set for other layers/versions, requests will fail with an integrity error; wrongly broad acceptance could hide mismatches.
- **Resolution (P02):** run `uv run python scripts/inspect_nc.py "data\cache\era5_land\raw\504d1adaca31d5f7.nc"`, record the exact `units`, tighten/extend `SOIL_WATER_UNITS` and tests to what is observed, verify layers 2 and 3 with one small live request each.
- **P02 evidence (2026-10-30; CONFIRMED, see `docs/DATA_VERIFICATION.md`):** `swvl1`/`swvl2`/`swvl3` all observed as `m**3 m**-3` (one cached file + two live single-month requests, 2 of 4 allowed); `tp` = `m`, `t2m` = `K` both directly observed. `SOIL_WATER_UNITS` tightened to exactly `{"m**3 m**-3"}` with a justification comment; tests accept the observed spelling and reject the three unobserved ones. A future spelling change now fails loudly with the actual string instead of being silently accepted or rejected.

### KI-06 — Soil-moisture anomaly pipeline missing (Medium) — ✅ RESOLVED 2026-10-30
- **Evidence:** Variables registered and series run; no pipeline analogous to `pipelines/temperature_anomaly.py`. Absolute ERA5-Land soil water has documented bias in at least one region (so anomalies, not absolute values, should be reported). Layer 4 intentionally excluded (documented depth inconsistency).
- **Dependencies:** KI-05.
- **Resolution (P04):** shared window-anomaly helper + soil-water pipeline, same safeguards.
- **P04 evidence (2026-10-30; CONFIRMED):** `indicators/window_anomaly.py` + `indicators/soil_moisture.py` + `pipelines/soil_moisture_anomaly.py` (layers 1–3, m3/m3 + standardized anomaly, no labels) with 40 new offline tests green and one live layer-1 run (exit 0, values in [0, 1], reported without interpretation). Layer 4 still excluded by design.

### KI-07 — ERA5-based indicators not exposed via API; latency (High for the demo) — ✅ RESOLVED 2026-10-30
- **Evidence:** ERA5 SPI, temperature anomaly and soil water exist as scripts only. CDS requests took ≈20–60 s each; a dropped connection triggered an automatic 120 s retry (≈5 min total, log "attempt 1 of 500"). CHIRPS cold SPI ≈1 min.
- **Impact:** A frontend cannot call these synchronously.
- **Resolution (P05):** job/polling pattern or cache-warming endpoints, explicit timeouts, progress states, and CORS. No endpoint may block indefinitely.
- **P05 evidence (2026-10-30; offline-tested):** ERA5 SPI / temperature / soil-moisture (layers 1–3) and the 4-indicator environmental bundle exposed as 202 + poll jobs (900 s timeout, progress, TTL); 26 new offline tests green; full suite green. Live uvicorn bundle check ran 2026-10-30 (downloads disabled, warm cache): POST → 202 in ~1.5 s, poll → succeeded 4/4 ok in ~21 s (CHIRPS SPI −0.517, ERA5 SPI −0.375, temp anomaly +2.218 °C, soil anomaly −0.0505 m3/m3; 30/30 years; ERA5 fallback used; zero external requests; no severity labels or leaks).

### KI-08 — CDS retry bounds unverified live (Medium) — signature half RESOLVED 2026-10-30, live behavior still open
- **Evidence:** `data/cds_client.py` passes `retry_max`, `sleep_max`, `timeout` only if the installed `cdsapi.Client.__init__` declares them; no log shows a warning or confirms the options applied. An earlier web search did not confirm Python option names (it returned a Rust port).
- **Impact:** A failing request could still retry for hours (500 × ≤120 s) on some versions.
- **Resolution (P02):** print the installed `cdsapi.Client` signature, confirm which options exist, and add a wall-clock deadline wrapper if they do not.
- **P02 evidence (2026-10-30; CONFIRMED, see `docs/DATA_VERIFICATION.md` §3):** installed cdsapi 0.7.7 declares all three as explicit `__init__` keywords (`timeout=60`, `retry_max=500`, `sleep_max=120`), so the app's bounds (5 / 60 s / 60 s) ARE passed — no deadline wrapper needed. New test `test_installed_cdsapi_exposes_all_retry_options` pins this against future cdsapi upgrades. Live retry behavior under a real failure remains UNVERIFIED (deliberately not attempted; the service carries throttling notices).

### KI-09 — CDS service notices and terms update (Medium)
- **Evidence:** Log banners: "Data Stores Service protection measures" and Terms of Use update on 28 Oct 2026 (continued use = acceptance; objections before 27 Oct).
- **Impact:** Possible throttling; owner action about terms.
- **Resolution:** owner reads notices; keep requests grouped/cached; no code change unless throttling is observed.
- **P02 observation (2026-10-30):** both live requests opened with the "Data Stores Service protection measures" banner (2026-10-06 notice); no throttling observed (~15 s and ~35 s queue+download).

### KI-10 — ERA5-Land masked grid point at the reference location (Medium)
- **Evidence:** (30.4, −9.6) has no value in any month; fallback used (30.5, −9.6), 7.8 km away. The pattern is consistent with a land–sea mask but this was never confirmed against ERA5-Land documentation.
- **Impact:** Values come from a neighbouring cell with possibly different elevation/coastal influence; reports must repeat the warning.
- **Resolution:** keep fallback opt-in and loudly reported; confirm mask explanation from official documentation when convenient.
- **P02 observation (2026-10-30):** both live swvl2/3 responses show the identical mask pattern ((30.4, -9.6) NaN, fallback to (30.5, -9.6)) — corroborated, still not confirmed against ERA5-Land documentation.

### KI-11 — CHIRPS remote cache not revalidated against ETag (Medium)
- **Evidence:** Captured ETags/Last-Modified show per-file revisions (2014-03 revised 2025-04-22; others 2024-11/12). Cached point records are never re-checked.
- **Impact:** Stale values after upstream revision.
- **Resolution:** optional `revalidate` path comparing ETag/Last-Modified with a HEAD request; record when values change. Low priority.

### KI-12 — SPI quality and labelling gaps (Medium)
- **Evidence:** Gamma fit has only descriptive KS D (0.093 CHIRPS, 0.103 ERA5) and no goodness-of-fit test; CHIRPS fitted vs empirical probability differ (0.303 vs 0.367 → SPI −0.517 vs −0.341); no SPI category labels because WMO bands were not verified.
- **Impact:** Users may over-read SPI; reports may want labels.
- **Resolution:** keep labels out until WMO bands are verified from the primary source (the WMO SPI User Guide, once obtained); consider a normality check of reference SPI; keep sensitivity (empirical vs gamma) in outputs.

### KI-13 — CHIRPS vs ERA5-Land disagreement unexplained; no ground truth (Medium)
- **Evidence:** Same season/point: totals 76.87 vs 59.15 mm, opposite monthly shapes; yearly correlation 0.77; SPI-3 −0.52 vs −0.38. Half-period change differences are within ~1 standard error.
- **Impact:** Any claim of a trend or a validated drought state would be unsupported.
- **Resolution:** present both products and their disagreement as uncertainty; compare against station/national data only if supplied. No trend claims.

### KI-14 — Everything is single-point; limited geography tested (Medium) — ✅ RESOLVED 2026-10-31 (4 real-data points; scope honestly bounded)
- **Evidence:** All analyses take one lat/lon; all real runs used one reference point (30.43, −9.61).
- **Impact:** "Global-first" is architectural only; coverage edge cases (high latitude, ocean, antimeridian, >60°N for CHIRPS) are tested synthetically, not on real data elsewhere.
- **Resolution (P14):** run the real pipelines at a few contrasting locations (one outside Africa) and report results and failures honestly; do not claim validation.
- **P14 evidence (2026-10-31; CONFIRMED):** real pipeline runs at Souss-Massa (reference), Punjab, Trøndelag (>60°N: CHIRPS `outside_coverage`, ERA5 ok), and an Atlantic masked point (ERA5 `missing_data`); results, failures, and non-claims in `docs/DEMO_RUNS.md`, snapshots in git-ignored `data/demo_snapshots/`. Four points are coverage probes, not validation.

### KI-15 — Prototype percentage anomaly endpoints can mislead (Low/Medium)
- **Evidence:** Percentage anomaly was +0.55 % while SPI was −0.52 against a longer reference; response labels state it is not a drought index.
- **Resolution:** frontend must show SPI first, show the percentage anomaly with its caveat, and always show the reference period.

### KI-16 — Duplicated window logic in `pipelines/spi_era5.py` and `temperature_anomaly.py` (Low) — ✅ RESOLVED 2026-10-30
- **Resolution (P04):** extract a shared helper when adding soil moisture; keep behavior and tests unchanged.
- **P04 evidence (2026-10-30; CONFIRMED):** `pipelines/era5_windows.py` holds the shared planning/fetch/grid-check logic; all three pipelines use it. Pre-existing temperature/SPI tests pass unmodified, plus a hand-computed regression guard pins identical temperature results.

---

## C. Scientific RAG

### KI-17 — Citations use PDF page indices, not printed page numbers (High for credibility) — RESOLVED 2026-10-30
- **Evidence:** `rag_search` returned "p. 114" for the 505-page FAO IDDP66 PDF, which has roman-numeral front matter, so the printed page differs.
- **Impact:** A reader opening the cited printed page lands in the wrong place.
- **Resolution (P06):** store PDF page labels where the PDF provides them (verify the pypdf page-label API from its docs), cite "PDF p. N (printed p. X)" or label ambiguity explicitly; extend `verify_citation` and tests.
- **P06 evidence 2026-10-30:** `Page.label` / `Chunk.label_start|end` from pypdf 6.21.3 `reader.page_labels`, presence-checked via `"/PageLabels" in reader.trailer["/Root"]` (`page_labels` synthesizes 1..N when absent, verified by probe). Citations render "PDF p. 114 (printed p. 96)" or "p. 7 (PDF index; no printed label)"; `verify_citation` flags label mismatches. Re-ingest: 830/854 pages carry printed labels. Tests use synthetic PDFs with labels stamped by pypdf's own `PdfWriter.set_page_label`.

### KI-18 — Missing documents (High for retrieval evaluation)
- **Evidence:** 3 manual downloads missing (`fao-wr22-deficit-irrigation-practices`, two ICARDA papers); WMO guide HTTP 503. 7 of 15 evaluation queries skipped.
- **P06 2026-10-30:** WMO retry SUCCEEDED (519,165 bytes, sha256 `eb3c3edf…`, 24 pages; title + WMO-No. 1090 on PDF p. 1). Corpus now 5 of 8 ingested; eval 10/15 with 5 skipped (all missing-manual queries). No mirror was added: the primary URL works, and the `publicdocs.mnr.gov.on.ca` URL stays unverified. Manuals still missing — owner action.
- **Resolution:** owner downloads manual PDFs into `data/corpus/raw/<doc_id>.pdf`; retry WMO later; a second WMO mirror was seen in a search (`publicdocs.mnr.gov.on.ca`) but is NOT verified as the genuine WMO file — verify before adding.

### KI-19 — Evaluation set is tiny and unreviewed (High)
- **Evidence:** Gold labels are document-level, written by Claude from abstracts/front matter; 8 evaluable queries; hit@1 = 1.00 (7 EN, 1 FR); the French hit is unexplained (possible lexical overlap). No page-level annotations.
- **P06 2026-10-30:** re-ran on 5 docs: 10 evaluable (9 EN, 1 FR), hit@1 = 1.00, 5 skipped with explicit reasons (q01, q03, q04, q13-fr, q15-ar — all need missing manuals). `scripts/rag_eval_review.py` writes git-ignored `data/corpus/eval_review.md` (top-3 + excerpts per query). Labels still owner-unreviewed — stays open.
- **Impact:** The numbers do not show retrieval quality.
- **Resolution (P06/P07):** owner reviews all 15 labels; add page-level annotations after reading; add queries for the new documents; report per-language results.
- **P07 2026-10-31:** labels still show no review traces in repo (no `relevant_pages`, no markers) — stays open. Three-way comparison is ceiling-flat (all arms 1.00); results classified exploratory in `docs/RAG_EVALUATION.md`, no improvement claimed.

### KI-20 — Bibliography chunks and wide page ranges degrade results (Medium) — tooling delivered 2026-10-30, default behavior unchanged
- **Evidence:** In `rag_search`, hit #2 was a reference-list chunk spanning PDF pages 115–119; hits #4–#5 were off-topic (maize leaf area; Iraq project list).
- **Resolution (P06):** detect and tag/down-weight reference sections, keep page ranges narrow, and re-evaluate. Do not drop content silently.
- **P06 evidence 2026-10-30:** `section_type` tag (year-density heuristic, tested; nothing deleted) + `exclude_reference` filter on both retrievers (default OFF), `rag_search --exclude-reference`, and `corpus_ingest --max-page-span`. Ref counts: IDDP66 188, WR45 275, WMO 2, ESSD 60, SciData 23 (of 1824). Spans default → cap-2: {1:947, 2:776, 3:63, 4:25, 5:11, 6:2} → {1:977, 2:834}, costing 13 short-dropped chunks. Canonical corpus keeps defaults (bare-command reproducibility). Known limitation: WR45's citation-dense historical chronology is over-tagged (visible in the review file); tightening was deferred to avoid hiding real bibliographies.

### KI-21 — No dense/cross-lingual retrieval (High) — dense mechanism delivered 2026-10-31, still open (no proven gain)
- **Evidence:** BM25 only. French/Arabic queries cannot match English text lexically. `HybridRetriever` has only been tested with stub retrievers.
- **Resolution (P07):** multilingual E5 (default `intfloat/multilingual-e5-small`, 384-d; `query: `/`passage: ` prefixes) with Qdrant local mode; hybrid via RRF; verify package APIs from docs; torch/model download is large; measure before/after on the same gold set. RRF constant k=60 is a convention from memory and must be tuned/justified, not assumed.
- **P07 evidence 2026-10-31:** E5-small-only `embeddings.py` + Qdrant-local `dense.py` (fingerprinted, idempotent `rag_index.py`) + `HybridRetriever` fusion, all tested with a fake embedder and `:memory:` Qdrant. CPU-only torch 2.15.0+cpu; model rev `614241f6…` (~470 MB); index 1824 points (~97 min build). BM25/dense/hybrid all 1.00 on 10 evaluable queries; k-sweep {10,30,60,100} flat — k=60 kept for lack of evidence. Cross-lingual benefit unproven (fr n=1, ar skipped). Stays open pending harder eval.

### KI-22 — pypdf font warnings flood ingest output (Low/Medium) — measured 2026-10-30, still open (noise only)
- **Evidence:** Hundreds of "fontTools is required to fully parse the encoding of a CFF Type1 font" lines; extracted text looked readable in search results.
- **Impact:** Noisy logs; possibly degraded extraction for some fonts (unmeasured).
- **Resolution (P06):** test whether installing `fonttools` changes extracted text; do not just suppress logging.
- **P06 evidence 2026-10-30:** sampled 30 pages per FAO PDF (first/middle/last) with pypdf 6.21.3: extracted-text sha256 byte-identical with fonttools 4.68.0 on an ephemeral `PYTHONPATH` (wheel deleted after) and without; only warnings changed (17 → 0 on the sample). pypdf uses fonttools solely for CFF `/FontFile3` parsing (`pypdf/_cmap.py`); IDDP66 has such fonts yet its text is unchanged. Decision: dependency NOT added; warning stays visible (cosmetic for this corpus, still noisy).

### KI-23 — Licences of several corpus sources UNVERIFIED (Medium)
- **Evidence:** Manifest marks WMO, ESSD and Sci Data licences as unverified; ICARDA records state CC-BY-NC-ND / CC-BY-SA; FAO items carry FAO notices.
- **Impact:** Redistribution/packaging risk for submission.
- **Resolution:** keep `data/corpus/` out of git and out of submission artifacts; verify licences on landing pages before any redistribution; owner decides.

### KI-24 — Manifest authors/year partially unverified (Low)
- **Evidence:** `unverified_fields` lists authors/year for some entries (e.g., ICARDA 1997 year and co-authors; WMO and journal author lists).
- **Resolution:** fill from the PDFs once downloaded.

---

## D. Model access, agent, recommendations, frontend

### KI-25 — Baseten model access details unverified; no LLM code exists (High) — adapter BUILT 2026-10-31, agent still not built
- **Evidence:** Owner states access to `meta-models/muse-spark-open-1026` with credits and rate limits. Endpoint, auth, tool calling, schema-constrained output, context size, and limits are unverified.
- **Impact:** Agent design depends on tool-calling support; an unsupported feature would change the architecture.
- **Resolution (P03):** verify from current Baseten documentation; run a tiny gated smoke script; record findings; design the adapter around verified capabilities with a deterministic fallback.
- **P03 evidence (2026-10-30; CONFIRMED, see `docs/LLM_PROVIDER_NOTES.md`):** base URL `https://inference.baseten.co/v1` + Bearer auth verified from official docs; `-1026` slug, tool-call round trip, and malformed-body error shape verified by one gated live run (5 calls, ≈$0.002); structured output verified *unsupported* for this model (docs: accepted but not enforced → P09 must validate client-side). Still open: numeric rate/context limits, credit budget, and all of P09/P10 (no adapter/agent code exists).
- **P09 evidence (2026-10-31; CONFIRMED, see `docs/LLM_PROVIDER_NOTES.md` §4):** adapter + versioned report schema + client-side validator + deterministic fallback + prompt templates built (`src/climateadapt/llm/`, 51 offline tests green, ruff clean); one gated live report call ran (HTTP 200 in 46.6 s, 26965/4000 tokens ≈$0.051, `finish_reason=length` → empty draft → labelled fallback served and re-validated clean). No model draft has ever been *accepted* yet: `max_tokens=4000` is far too small for this reasoning model on a ~27k prompt, so a larger-budget retry (owner-approved) is needed before P10. Still open: numeric rate/context limits, credit budget, accepted-draft behavior, and all of P10 (no agent code exists).
- **P10 evidence (2026-10-31; CONFIRMED, see `docs/AGENT_WORKFLOW.md`):** fixed 7-stage pipeline built (`src/climateadapt/agent/`, 22 offline tests green, ruff clean; LangGraph 1.2.19 checked via PyPI, not adopted by recorded decision); one gated live run produced a full draft (97 s, 26965/15087 tokens ≈$0.098) that the validator rejected with 44 problems → labelled fallback served and re-validated clean. Still open: numeric rate/context limits, credit budget, and KI-35 (no draft accepted yet).

### KI-26 — No recommendation engine or evidence-backed catalog (High) — ✅ RESOLVED 2026-10-31 (engine done; catalog small by design)
- **Evidence:** Not started. Corpus currently covers irrigation-related practices (deficit and supplemental irrigation, crop water response) and indicator/dataset documentation; it contains little on other adaptation options (e.g., varieties, sowing dates, mulching, water harvesting).
- **Impact:** Catalog entries would be unsupported unless more sources are added.
- **Resolution (P08):** build the catalog only from documents in the corpus with explicit unknowns; owner supplies/approves additional sources first.
- **P08 evidence (2026-10-31; CONFIRMED):** `src/climateadapt/recommend/` delivers the versioned catalog (v1: 2 supported irrigation entries + 1 `needs_evidence`), deterministic hard constraints with machine-readable reasons, transparent ranking (weights 0.5/0.3/0.2, full breakdowns, id-ordered ties), and `scripts/validate_catalog.py` (0 errors, 0 warnings against the ingested corpus). 80 new offline tests green; no efficacy/cost/benefit figure anywhere (all `unknown`). Catalog growth still needs owner-supplied sources (see KI-18 manuals); non-irrigation options remain unranked by design. Details: `docs/RECOMMENDATION_ENGINE.md`.

### KI-27 — No frontend; blueprint says Streamlit (High) — ✅ RESOLVED 2026-10-31 (input/analysis UI; P13 extends it)
- **Evidence:** No `frontend/`; blueprint and early requirements named Streamlit/Plotly. Requirement is now React + Vite.
- **Resolution (P11–P13):** React + Vite; remove stale Streamlit mentions in docs.
- **P12 evidence (2026-10-31; CONFIRMED):** `frontend/` delivers the React + Vite input/analysis screens (typed client from `docs/openapi.json`, scenario form, polling, indicator cards + reference chart, error-code mapping; 42/42 Vitest green, tsc/eslint/build clean, verified against real backend outputs — see IMPLEMENTATION_STATUS §2.14). No Streamlit anywhere in code; remaining "Streamlit" hits are historical records (audit report, task prompts, decision log) plus the standing AGENTS.md rule. P13 adds the recommendations/report UI.

### KI-28 — API has no CORS, no auth, no rate limiting, synchronous long calls (Medium/High for frontend) — P05 parts DONE 2026-10-30, auth/rate limiting still open
- **Evidence:** `api/main.py` (as delivered) has no `CORSMiddleware`; endpoints are synchronous; the shared client has no shutdown hook; offline-mode error text includes a local cache path.
- **Resolution (P05/P11):** CORS for the dev origin, request timeouts/jobs, lifespan shutdown, remove local paths from client-facing messages.
- **P05 evidence (2026-10-30; offline-tested):** CORS from settings (Vite origin default) with preflight tests; new endpoints are 202 + poll jobs (timeout/TTL/workers); lifespan closes the CHIRPS store and cancels queued jobs; local path removed from the offline error text. Remaining: no auth, no rate limiting (P11 scope). Submission backpressure added (follow-up 2026-10-30): a full store returns 503 `server_busy` instead of growing.
- **P11 evidence (2026-10-31):** CORS `allow_methods` extended with DELETE (preflight test added); request bodies capped at 1 MB via middleware (413 `request_too_large`, new deliberately-added code); scenario CRUD behind the same error contract. Still open: **no auth, no rate limiting** — now a documented limitation (README + route descriptions); do not expose beyond localhost.

### KI-29 — No scenario persistence (Medium) — ✅ RESOLVED 2026-10-31
- **Evidence:** No database or history store. Blueprint calls for PostgreSQL/PostGIS.
- **Resolution (P11):** minimal, justified persistence (SQLite for the demo unless the owner wants PostgreSQL now).
- **P11 evidence (2026-10-31):** `ScenarioStore` protocol + stdlib-SQLite store (WAL, `user_version` migrations, schema v1, thread-safe) persisting inputs, bundle, ranking, report, trace, status, and timestamps; scenario CRUD + paginated history + 204 delete; PostgreSQL stays owner-optional (seam is the protocol). Sync store tests ran green; TestClient API tests written but sandbox-unrunnable (see KI-34 note).

---

## E. MLOps and scope

### KI-30 — Nine of eleven named MLOps tools not started (Medium; depends on rubric)
- **Evidence:** Only Pytest and FastAPI exist. No Docker, CI, MLflow, Optuna, Airflow, PostgreSQL, Prometheus, Evidently, Grafana.
- **Resolution (P15):** Docker + CI first; others only as thin, genuinely functioning integrations (e.g., MLflow/Optuna on retrieval evaluation, Prometheus `/metrics`, Evidently on input-data drift). Never claim an integration that does not run.
- **P15 evidence (2026-11-01):** backend + frontend/nginx Dockerfiles, compose stack (health check, `./data` bind-mount), `.dockerignore`, `.env.docker.example`, and a CI workflow (ruff, offline pytest, compose-config check, frontend lint/test/build, uv/npm caching) are authored; `docker compose config --quiet` passes (Compose v5.6.0, CONFIRMED). Image build, container start, and CI's first GitHub execution are UNVERIFIED (no Docker daemon in the agent environment) — the owner must run `docker compose up --build` and report. Owner chose core-only: Prometheus, MLflow, Optuna, Evidently, Airflow, Grafana, PostgreSQL are explicitly NOT IMPLEMENTED.

### KI-31 — Computer-vision milestone undecided (Medium)
- **Evidence:** Deferred by Claude's proposal (RAG first); the owner has not confirmed. CropHarvest/PyTorch work is heavy and only loosely tied to the adaptation recommendation.
- **Resolution:** owner decides (P16). If included, never present crop classification as proof of drought damage.

### KI-32 — Judging rubric and deadline unknown (High for planning)
- **Evidence:** Not in the blueprint or conversation.
- **Resolution:** owner supplies; revise `IMPLEMENTATION_ROADMAP.md` priorities accordingly.

### KI-33 — README stale (Low/Medium)
- **Evidence:** No RAG commands, no soil-moisture/CDS-retry notes.
- **Resolution (P06, P17):** update alongside each change.

### KI-34 — Windows/console quirks (Low)
- **Evidence:** RAG scripts call `sys.stdout.reconfigure(encoding="utf-8")` for Arabic/French output; earlier scripts do not. Paths in docs use backslashes.
- **Resolution:** keep commands PowerShell-safe; check encoding handling when scripts print non-ASCII.
- **Sandbox note (P11, 2026-10-31):** the agent sandbox blocks `listen()`/`socketpair()` (WinError 10013), which breaks `asyncio`, Starlette `TestClient`, and `uvicorn` entirely. Pre-existing and environmental: untouched `tests/test_api_era5.py` fails identically. P11's 14 TestClient tests are therefore written-but-unrun here; the same behaviors were verified with a throwaway direct-call probe (all passed). The owner must run `uv run pytest tests/test_api_scenarios.py` and the README manual calls on their machine.

### KI-35 — Model invents tool-output ids; prompt never states the registry vocabulary (High for draft acceptance)
- **Evidence (P10 live run 2026-10-31; CONFIRMED):** the first full draft used `environmental_bundle` and `environmental_bundle:entries[N].result.<field>` instead of the registry ids (`bundle`, `chirps_spi`, …) — 22 of its 44 validator problems — plus undeclared numbers, 2 altered citations, missing ranking/constraints refs, and 2 efficacy claims. The prompt shows TOOL DATA as raw bundle/ranking JSON, which does not expose the `(output_id, field)` vocabulary.
- **Impact:** No model draft has ever been accepted; every live run serves the fallback. Validator enforcement is proven, but draft acceptance is not.
- **Resolution:** add the registry map as an explicit TOOL DATA block plus one in-context `numbers[]` example; retry live once with owner approval and report acceptance honestly. Do not loosen the validator to fit the model.
