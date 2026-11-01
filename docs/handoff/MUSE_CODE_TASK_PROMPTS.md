# Muse Code Task Prompts

> Historical record (P-final 2026-11-01): P00–P16 are done; P17 is this task. Prompt texts below are frozen as-issued (including their "verify first" instructions) and may describe long-superseded states — current truth lives in `IMPLEMENTATION_STATUS.md` and the repository. Do not re-run old prompts against the current tree.

Copy one prompt at a time into Muse Code. **Do not start a prompt until the previous one is reviewed and its tests were actually run.** Each prompt is standalone but assumes the repository contains `AGENTS.md` and `docs/handoff/*`. The handoff documents were written without repository access, so each prompt tells Muse Code to verify against the real tree first.

Order: P00 → P01 → P02 → P03 → P04 → P05 → P06 → P07 → P08 → P09 → P10 → P11 → P12 → P13 → P14 → P15 → (P16 optional) → P17. See `IMPLEMENTATION_ROADMAP.md` for dependencies, tiers and parallelism.

Windows/PowerShell commands throughout. "Report" always means the block defined in `AGENTS.md` §12 with **actual** command output.

---

## P00 — Read-only audit and baseline test run (NO code changes)

```
You are working in the ClimateAdapt Lab repository. Read AGENTS.md and docs/handoff/*.md first.

OBJECTIVE
Establish ground truth about the repository and its test status. The handoff docs were written from conversation history without repository access, so treat them as claims to check, not facts.

HARD RULES
- Do NOT modify, create, or delete any file except creating docs/handoff/AUDIT_REPORT.md.
- Do NOT call the network or any live service: do not run scripts/corpus_fetch.py, scripts/chirps_*.py, scripts/era5land_cli.py, scripts/temperature_anomaly.py, scripts/spi_*.py, scripts/compare_chirps_era5.py, or anything that needs credentials. Do not read or print .env, ~/.cdsapirc, or any secret.
- Do not fix anything. Record it.

STEPS
1. Record git state: branch, `git status`, last 15 commits (if the directory is not a git repo, say so).
2. List tracked files (`git ls-files`, or a directory listing if no git) and reconcile against docs/handoff/IMPLEMENTATION_STATUS.md section 2: missing files, extra files, renamed files. Note whether frontend/ exists and whether scripts/chirps_layout_probe.py still exists.
3. Safety check: confirm .env, data/, *.pdf, ~/.cdsapirc-like files are NOT tracked; grep the tree for hard-coded keys/tokens (report file/line only, never the secret value).
4. Run `uv sync --extra dev`, then the full suite `uv run pytest` and `uv run ruff check .`. Capture the final summary line, every failing test name, and the first relevant lines of each traceback. Note total runtime and warnings.
5. Check whether the four fixes described in docs/handoff/KNOWN_ISSUES.md KI-01 are already present (DEFAULT_CHUNKING_PARAMS in src/climateadapt/rag/chunking.py and ingest.py; the two test edits in tests/test_rag_text_chunking.py).
6. Import check without a server: `uv run python -c "from climateadapt.api.main import app; print(sorted(r.path for r in app.routes))"`. Compare to the four routes documented.
7. Review config.py settings vs .env.example; list undocumented or stale items. Check README.md for stale content (RAG commands, Streamlit mentions).
8. Check layering: list any import where indicators/ imports from data/, api/, or rag/ (should not), or tests that touch the network.
9. For each claim in IMPLEMENTATION_STATUS.md and KNOWN_ISSUES.md, mark CONFIRMED (you verified), CONTRADICTED, or NOT VERIFIABLE OFFLINE.

DELIVERABLE: docs/handoff/AUDIT_REPORT.md with: git state; file reconciliation table; verbatim pytest/ruff results; list of verified problems (each with file/line/evidence) separated from observations; discrepancies with handoff docs; recommended minimal fix list for the next task.

ACCEPTANCE: report contains real command output; no tracked file other than AUDIT_REPORT.md changed (`git status` proves it); every statement labeled CONFIRMED/CONTRADICTED/NOT VERIFIABLE.
VERIFY: `git status --short` (only AUDIT_REPORT.md new).
RISKS: suite takes ~5-8 minutes; do not interrupt it. If uv sync fails, report the exact error and stop.
DOCS: none besides AUDIT_REPORT.md.
Finish with the AGENTS.md section 12 report.
```

## P01 — Fix only the problems verified by the audit

```
Read AGENTS.md, docs/handoff/AUDIT_REPORT.md, and docs/handoff/KNOWN_ISSUES.md (KI-01..KI-04).

OBJECTIVE
Reach a verified green baseline (all tests pass, ruff clean) with the smallest possible changes. No features, no refactors, no dependency upgrades, no formatting churn.

PREREQUISITE: P00 audit report exists.

SCOPE
Fix only items listed as verified problems in AUDIT_REPORT.md. Expected candidates (apply ONLY if the audit shows they are still failing):
- ruff B008 in src/climateadapt/rag/chunking.py and src/climateadapt/rag/ingest.py: add module constant `DEFAULT_CHUNKING_PARAMS = ChunkingParams()` (after the dataclass) and use it as the default in chunk_document and ingest_document; update the import in ingest.py.
- tests/test_rag_text_chunking.py::test_tampering_and_wrong_pages_fail_verification: replace the "word inserted before the chunk" case with an edit INSIDE the chunk (`pages[0].text.replace("w0030", "w9999")`). Rationale: verify_chunk_provenance checks content re-derivation, not offsets.
- tests/test_rag_text_chunking.py::test_number_heavy_windows_are_dropped_and_counted: use `* 20` instead of `* 25` in the prose page (200 words -> exactly two 100-word windows).
For each fix state whether the SOURCE or the TEST was wrong, with evidence. Do not weaken a test to make it pass; if a failure reveals a real bug, fix the code and say so.

OUT OF SCOPE: new features; touching the Starlette/httpx warning beyond investigating (KI-04); speeding tests (KI-03).

TESTS/ACCEPTANCE
- `uv run pytest` fully green; report the exact final line (counts, duration).
- `uv run ruff check .` prints "All checks passed!".
- Diff is limited to files needed; list them.

VERIFY: `uv run pytest tests/test_rag_text_chunking.py`, then `uv run pytest`, then `uv run ruff check .`.
RISKS: other failures may appear once these are fixed; fix only verified ones and list the rest as new issues.
DOCS: update IMPLEMENTATION_STATUS.md section 1 and KNOWN_ISSUES.md (mark KI-01 resolved only with evidence).
Finish with the AGENTS.md section 12 report.
```

## P02 — Resolve data-units and CDS-client uncertainties (live, tiny)

```
Read AGENTS.md; docs/handoff/KNOWN_ISSUES.md KI-05, KI-08, KI-09, KI-10; src/climateadapt/data/era5_land.py, data/cds_client.py, scripts/inspect_nc.py.

OBJECTIVE
Replace assumptions about ERA5-Land NetCDF units and CDS-client retry behavior with observed facts, so later indicators rest on verified units.

PREREQUISITES: P01 green baseline; CDS credentials already configured in ~/.cdsapirc (do not read it); dataset terms accepted; CLIMATEADAPT_ALLOW_DOWNLOADS=true.

WORK
1. Run `uv run python scripts/inspect_nc.py "data\cache\era5_land\raw\504d1adaca31d5f7.nc"` (swvl1 file). Record variable name and the exact `units` string. Do the same for one total_precipitation raw file and one 2m_temperature raw file already in data/cache/era5_land/raw/.
2. Update SOIL_WATER_UNITS (and temperature/precipitation unit sets if needed) to what was observed; keep extra spellings only with a written justification; adjust tests accordingly.
3. Verify layers 2 and 3: one live request each (single month, reference point lat 30.43 lon -9.61, use --land-fallback-km 15) via scripts/era5land_cli.py. Record units/variable names. LIMIT: at most 4 live CDS requests in total; report each.
4. Print the installed cdsapi version and the signature of cdsapi.Client.__init__ (`inspect.signature`). Record which of retry_max / sleep_max / timeout exist. If the options do NOT exist, add a bounded wall-clock deadline around download (e.g., run the call in a worker with a timeout) in data/cds_client.py with offline tests using a fake client that hangs; if they DO exist, add a test asserting they are passed.
5. Write docs/DATA_VERIFICATION.md: observed facts with dates, commands, and raw outputs (no secrets).

OUT OF SCOPE: new indicators, API changes, interpreting soil-moisture values.

ACCEPTANCE: documented exact units; tests updated and green; retry behavior documented; no secrets in outputs; all live calls counted in the report.
VERIFY: `uv run pytest tests/test_era5_land.py tests/test_era5_soil_moisture.py tests/test_cds_client.py`, then full `uv run pytest`, `uv run ruff check .`.
RISKS: CDS queueing/throttling (notice: "Data Stores Service protection measures"); if a request fails, report the error verbatim instead of retrying repeatedly.
DOCS: KNOWN_ISSUES (KI-05, KI-08), IMPLEMENTATION_STATUS, docs/DATA_VERIFICATION.md.
Finish with the AGENTS.md section 12 report.
```

## P03 — Baseten / Muse Spark capability verification spike

```
Read AGENTS.md section 8 and docs/handoff/PROJECT_CONTEXT.md section 4; src/climateadapt/config.py.

OBJECTIVE
Determine, from current official documentation and a tiny gated live test, exactly how the application may call `meta-models/muse-spark-open-1026` on Baseten, and which capabilities (tool calling, structured output, streaming, limits) are really available. Do NOT build the adapter or agent yet.

PREREQUISITES: P01 green. Owner provides the Baseten API key through an environment variable (Muse Code's own authentication is separate and must not be reused). Ask the owner for the credit/rate-limit budget before live calls.

WORK
1. Read current Baseten documentation for this model/route. Record in docs/LLM_PROVIDER_NOTES.md (with URLs and access date): base URL, authentication header, request/response shape, model identifier string, streaming, tool/function calling, JSON-schema or structured output, max context/output tokens, documented rate limits, error codes, pricing/credits if stated. Mark everything not found as UNVERIFIED. Do not guess endpoints or parameters.
2. Add non-secret settings fields to config.py (base URL, model id default `meta-models/muse-spark-open-1026`, optional api key as a secret type that never prints) plus offline tests proving the key is not exposed in repr/logs. Document the env var names in .env.example (no values).
3. Create scripts/llm_smoke.py, runs ONLY if an explicit env flag (e.g., CLIMATEADAPT_RUN_LIVE_LLM=1) and the key are set. At most 5 calls: (a) trivial completion; (b) structured JSON output test against a small schema; (c) tool-call test if documented as supported; (d) one deliberately malformed-request test to observe the error shape; (e) optional rate-limit probe only if safe. Print status, latency, token usage if returned, and truncated responses. Never print the key.
4. Run it once and record results; if no key is available, say "not run" and why.

OUT OF SCOPE: provider adapter, agent graph, prompts for the real report, UI.

ACCEPTANCE: LLM_PROVIDER_NOTES.md separates VERIFIED (with evidence) from UNVERIFIED; smoke results recorded or honestly "not run"; no secret in repo or logs; offline tests green.
VERIFY: `uv run pytest`, `uv run ruff check .`, then (gated) `uv run python scripts/llm_smoke.py`.
RISKS: rate limits/credits; model may not support tools or schema-constrained output -> record clearly so P09/P10 can choose a fixed-pipeline design.
DOCS: IMPLEMENTATION_STATUS, KNOWN_ISSUES (KI-25), PROJECT_CONTEXT section 4.
Finish with the AGENTS.md section 12 report, including calls made and any usage/credit information returned.
```

## P04 — Soil-moisture anomaly and shared window-anomaly helper

```
Read AGENTS.md; docs/handoff/KNOWN_ISSUES.md KI-05, KI-06, KI-16; src/climateadapt/indicators/temperature.py, pipelines/temperature_anomaly.py, pipelines/spi_era5.py, data/era5_land.py, tests/test_temperature*.py, tests/era5_helpers.py. Read docs/DATA_VERIFICATION.md (from P02).

OBJECTIVE
Add the soil-moisture anomaly indicator (ERA5-Land volumetric soil water, layers 1-3) with the same safeguards as temperature, and remove duplicated window logic without changing existing behavior.

PREREQUISITES: P02 done (units verified).

WORK
1. Extract a generic window-anomaly calculation (day-weighted window mean, reference-year selection with exclusion-not-imputation, anomaly, standardized anomaly, mid-rank percentile, validity checks supplied by the caller) into src/climateadapt/indicators/window_anomaly.py. Make temperature.py a thin wrapper keeping its public API, field names and results identical.
2. Add pipelines/soil_moisture_anomaly.py for variables volumetric_soil_water_layer_1/2/3: fail-fast validation, target window first, grouped reference requests, same-grid-point enforcement, opt-in land fallback, provenance, limitations. Limitations must state: reanalysis, absolute ERA5-Land soil water can be biased so only anomalies are reported, layer depths (0-7, 7-28, 28-100 cm), monthly means cannot show timing, soil water anomaly is not crop-water stress by itself. Output is in m3/m3 and a standardized anomaly; no category labels.
3. Optionally refactor pipelines/temperature_anomaly.py and spi_era5.py to share window-assembly code ONLY if all existing tests pass unchanged; otherwise leave them.
4. scripts/soil_moisture_anomaly.py (like scripts/temperature_anomaly.py).
5. Offline tests with the synthetic NetCDF builder: hand-checkable anomaly values, missing reference years, masked point + fallback, mixed grid point refusal, invalid parameter handling, unit mismatch. Existing tests must pass unmodified.
6. One live run at lat 30.43 lon -9.61 (layer 1; 2-3 CDS requests max). Report values and that they lie in [0,1]; do not interpret them as wet/dry.

OUT OF SCOPE: API endpoints (P05), root-zone weighted averages, layer 4, drought classification.

ACCEPTANCE: new tests green; all pre-existing tests green and unmodified; behavior of temperature outputs identical (add a regression test comparing before/after on the same synthetic data).
VERIFY: `uv run pytest tests/test_temperature.py tests/test_temperature_pipeline.py`, new tests, then full `uv run pytest` and `uv run ruff check .`.
RISKS: subtle behavior change in refactor; keep changes minimal and covered.
DOCS: IMPLEMENTATION_STATUS, KNOWN_ISSUES (KI-06, KI-16), README scripts section.
Finish with the AGENTS.md section 12 report.
```

## P05 — Environmental API: ERA5 endpoints, job pattern, CORS, analysis bundle

```
Read AGENTS.md section 10; src/climateadapt/api/main.py, api/dependencies.py, schemas*.py, all pipelines/*.py; docs/handoff/KNOWN_ISSUES.md KI-07, KI-14, KI-15, KI-28.

OBJECTIVE
Expose the complete environmental analysis through a stable, non-blocking FastAPI contract that a React frontend and the agent can consume, including one "environmental bundle" that never hides failures.

PREREQUISITES: P01 green; P04 done (or explicitly scope the soil-moisture indicator out of the bundle).

WORK
1. Routes (all /v1, Pydantic request/response models, OpenAPI examples): ERA5 SPI, ERA5 temperature anomaly, ERA5 soil-moisture anomaly (if P04 done), and POST /v1/analysis/environmental-bundle for location + target window + timescale + reference period. The bundle returns, per indicator: status (ok / undefined / failed / skipped), result or error `type` and message, provenance, limitations, and the requested/used coordinates and grid cells. It must never merge indicators into a composite score and never add severity labels.
2. Long-running work: choose and implement a job pattern (POST returns 202 + job id; GET /v1/jobs/{id} returns status/progress/result/error) using an in-memory store and bounded worker threads, per-job timeout and cancellation of futures on shutdown. No HTTP call may block beyond a configured limit. Warm-cache calls should still return quickly.
3. CORS via settings (explicit list of origins; default the Vite dev origin) and a test. Add a FastAPI lifespan that closes shared clients. Remove local filesystem paths from client-facing error messages.
4. Keep existing endpoints and error codes backward compatible; add new codes only deliberately and document them.
5. Tests: TestClient with fake ERA5/CHIRPS clients (existing fixtures), job lifecycle (success, failure, timeout, unknown id), CORS preflight, bundle with one failing indicator (must report the failure), validation errors never echoing input, OpenAPI contains routes.
6. Manual live check (cache warm): call the bundle for lat 30.43, lon -9.61, window ending 2024-03, timescale 3, reference 1991-2020; report timings and the full status block (not interpretation).

OUT OF SCOPE: persistence (P11), RAG endpoints, LLM calls, frontend.

ACCEPTANCE: all tests green; bundle demonstrably reports partial failure; no endpoint blocks past the configured timeout; OpenAPI saved to docs/openapi.json.
VERIFY: `uv run pytest tests/test_api*.py` + new tests, full `uv run pytest`, `uv run ruff check .`, `uv run uvicorn climateadapt.api.main:app --reload` and a manual call.
RISKS: threads + GDAL/xarray thread safety (check CHIRPS remote reads under concurrency); CDS throttling; memory growth of in-memory jobs (add TTL).
DOCS: README endpoints, IMPLEMENTATION_STATUS, KNOWN_ISSUES (KI-07, KI-28), docs/openapi.json.
Finish with the AGENTS.md section 12 report.
```

## P06 — RAG hardening: citations, completeness, reviewed gold set

```
Read AGENTS.md; src/climateadapt/rag/*.py; corpus/manifest.json; corpus/eval/queries.json; scripts/corpus_*.py, rag_*.py; docs/handoff/KNOWN_ISSUES.md KI-17..KI-24.

OBJECTIVE
Make retrieval results trustworthy and evaluable before adding dense retrieval: correct citation pages, complete corpus, cleaner chunks, and a gold set reviewed by the owner.

PREREQUISITES: P01 green. Owner has placed the three manual PDFs in data/corpus/raw/ with the exact names from corpus/manifest.json (ask the owner; do not download them yourself) and may supply a verified WMO PDF. Re-running ingestion regenerates data/corpus/processed/ (git-ignored).

WORK
1. Page labels: check the installed pypdf documentation for reading PDF page labels (do not guess the API). Store both the PDF page index and the printed label when available; citations must show e.g. "PDF p. 114 (printed p. 96)" or state when no label exists. Update verify_citation and tests (synthetic PDFs with labels if possible).
2. Reference-section handling: detect bibliography/reference chunks heuristically, tag them (e.g., section_type) and let retrievers down-rank or filter them via an explicit option. Do not delete content silently; report counts per document.
3. Narrow page ranges: add a chunking option/flag so chunk page spans stay small, and report the distribution of page spans before/after.
4. Extraction noise: measure whether installing `fonttools` changes extracted text for the FAO PDFs (diff a sample of pages) and decide with evidence; do not simply hide the warning.
5. Fetch robustness: retry once on 5xx; retry the WMO download; add a mirror to the manifest ONLY after verifying it is the genuine WMO document (hash/title/page count); keep licence fields honest.
6. Gold-set review: generate a local review file data/corpus/eval_review.md (git-ignored; short excerpts only) listing each query with its top-3 results so the owner can correct relevant_doc_ids and add relevant_pages in corpus/eval/queries.json. Do NOT edit gold labels yourself.
7. Re-ingest all available documents and re-run `uv run python scripts/rag_eval.py`; report per-language results and the explicit list of skipped queries. Do not tune parameters against the gold set in this task.
8. Add RAG commands to README.md.

OUT OF SCOPE: dense retrieval, API routes, recommendations, committing any PDF or extracted text.

ACCEPTANCE: citation output distinguishes PDF index and printed label; reference chunks tagged; manifest/doc tests green; documents ingested count and eval coverage reported; README updated.
VERIFY: `uv run pytest tests/test_rag_*.py`, full suite, ruff, `uv run python scripts/corpus_ingest.py`, `uv run python scripts/rag_search.py "..."`, `uv run python scripts/rag_eval.py`.
RISKS: processed-data schema changes require re-ingest; licences of some sources are unverified; never commit corpus text.
DOCS: KNOWN_ISSUES (KI-17..KI-24), IMPLEMENTATION_STATUS, README, manifest unverified_fields.
Finish with the AGENTS.md section 12 report.
```

## P07 — Dense retrieval (multilingual E5 + Qdrant) and hybrid evaluation

```
Read AGENTS.md; src/climateadapt/rag/retrieval.py, fusion.py, evaluation.py; docs/handoff/KNOWN_ISSUES.md KI-19, KI-21; the P06 evaluation output.

OBJECTIVE
Add a dense retriever and measure BM25 vs dense vs hybrid honestly on the reviewed gold set, including French and Arabic queries.

PREREQUISITES: P06 done; owner has reviewed corpus/eval/queries.json; owner agrees to a large dependency/model download (torch + sentence-transformers + model weights, hundreds of MB). Verify current docs for sentence-transformers and qdrant-client and record versions.

WORK
1. src/climateadapt/rag/embeddings.py: wrapper for `intfloat/multilingual-e5-small` by default (384-d; configurable to base/large) using the REQUIRED prefixes "query: " for queries and "passage: " for chunks, L2-normalized, batched, lazy-imported so the base package and tests run without torch.
2. src/climateadapt/rag/dense.py: DenseRetriever using Qdrant LOCAL mode persisted under data/qdrant/ (no server), cosine distance, payload = chunk_id/doc_id/pages; collection name derived from model + chunk parameters; idempotent indexing and a rebuild command; scripts/rag_index.py.
3. Hybrid: plug DenseRetriever and Bm25Retriever into the existing HybridRetriever/RRF. Keep component ranks/scores in results.
4. Evaluation: extend scripts/rag_eval.py to compare bm25 / dense / hybrid, per language, with the same metrics. RRF k: report an exploratory sweep (e.g., k in {10, 30, 60, 100}) but state the small-n caveat; choose a default and justify; do not claim improvements without numbers.
5. Offline tests with a deterministic fake embedder (no torch): indexing idempotency, prefix usage, normalization, query path, hybrid fusion with real retrievers, Qdrant in-memory mode. One real-model smoke test gated by an env flag.

OUT OF SCOPE: reranking models, query translation, API routes, changing chunking.

ACCEPTANCE: dense and hybrid evaluable via scripts; results table in docs/RAG_EVALUATION.md with the exact commands, data (documents ingested), and limitations; tests green offline.
VERIFY: `uv sync --extra dev` (after dependency change), `uv run pytest tests/test_rag_*.py`, full suite, ruff, `uv run python scripts/rag_index.py`, `uv run python scripts/rag_eval.py`.
RISKS: model download size and CPU speed (index time; report it); Windows/torch wheel issues; metric overfitting on ~15 queries.
DOCS: README RAG section, KNOWN_ISSUES (KI-19, KI-21), IMPLEMENTATION_STATUS, docs/RAG_EVALUATION.md.
Finish with the AGENTS.md section 12 report.
```

## P08 — Evidence-linked intervention catalog and deterministic recommendation engine

```
Read AGENTS.md section 7; docs/handoff/KNOWN_ISSUES.md KI-26; corpus/manifest.json; the P05 bundle schema; src/climateadapt/rag/citations.py.

OBJECTIVE
Build a structured, versioned intervention catalog with explicit unknowns, deterministic hard constraints, and transparent ranking. No LLM involved. No invented efficacy, cost or benefit figures.

PREREQUISITES: P06/P07 done; the OWNER has approved which adaptation options may be included and supplied/approved the supporting documents (the current corpus mainly supports irrigation-related options). Entries without corpus evidence must be marked needs_evidence and excluded from ranking.

WORK
1. Package src/climateadapt/recommend/: Pydantic schema + data file (catalog JSON). Each intervention: id, name, category, description, applicability constraints (crop types, water access, soil, climate regime, farm scale...) where every attribute can be `unknown`, benefit/cost/risk fields that are `unknown` unless a cited source states them, evidence links (manifest doc_id + PDF page + short citation reference, no long quotes), and an evidence_strength rubric defined in code and documented.
2. constraints.py: deterministic hard constraints (e.g., an irrigation option is excluded when no water source is available). Output: eligible and excluded options with machine-readable reasons.
3. ranking.py: transparent scoring from documented components (e.g., indicator relevance, evidence strength, constraint fit). Every score must expose its component breakdown and inputs. Ties deterministic. No hidden weights.
4. Input: scenario context (crop, water access flags, season, location) + environmental bundle summary. Output: ranked options, exclusions with reasons, unknowns, and evidence references.
5. scripts/validate_catalog.py: checks every doc_id/page exists in the manifest/ingested corpus and flags unsupported claims.
6. Tests: schema validation, unknown handling, each constraint, exclusion reasons, ranking determinism, evidence validation failures, regression fixtures. Offline.

OUT OF SCOPE: LLM calls, UI, area analysis, cost-benefit modelling, any claim of yield benefit not stated in a cited source.

ACCEPTANCE: catalog validates against the corpus; ranking explanations are complete; unknowns never silently become zeros; tests green.
VERIFY: `uv run pytest tests/test_recommend*.py`, full suite, ruff, `uv run python scripts/validate_catalog.py`.
RISKS: thin evidence -> small catalog; resist padding it with memory-based content.
DOCS: docs/RECOMMENDATION_ENGINE.md (rubric, weights, limits), IMPLEMENTATION_STATUS, KNOWN_ISSUES (KI-26).
Finish with the AGENTS.md section 12 report.
```

## P09 — LLM provider adapter, report schema, and citation/number validator

```
Read AGENTS.md sections 1, 7, 8; docs/LLM_PROVIDER_NOTES.md (from P03); the P05 bundle and P08 ranking schemas; src/climateadapt/rag/citations.py.

OBJECTIVE
Isolate model calls behind an adapter and guarantee that any model-written report is schema-valid and traceable to deterministic outputs and retrieved sources before a user sees it.

PREREQUISITES: P03 verified provider facts; P05 and P08 done.

WORK
1. src/climateadapt/llm/: LLMProvider protocol; BaseTen-backed provider implemented ONLY against the verified API from LLM_PROVIDER_NOTES.md (bounded retries/backoff, timeouts, rate-limit handling, secret-safe logging, token/usage accounting if returned); FakeProvider for tests. No other provider/model ID unless verified.
2. Report schema (Pydantic): summary, environmental findings, evidence, ranked recommendations, excluded options, limitations, assumptions, data coverage, provenance references. Every statement carries evidence_ids (retrieved chunk ids) and/or tool_output_ids; numbers appear only through structured fields copied from tool outputs.
3. validator: reject or strip claims whose evidence ids are unknown; verify numbers in prose match tool outputs; require limitations and provenance; forbid unsupported efficacy/cost claims and severity labels; verify each citation via rag.citations.verify_citation. Validation failure yields a deterministic fallback report (no AI narrative) clearly labelled.
4. Prompt templates in the repo with an explicit instruction hierarchy; tool outputs are data, never instructions (prompt-injection safe handling of retrieved text).
5. Tests: fake provider with well-formed output; fabricated citation; altered number; missing limitations; unknown evidence id; injection text inside a retrieved chunk; provider timeout/rate limit; fallback path.
6. One gated live call producing a report from a stored real bundle; report latency and usage.

OUT OF SCOPE: agent graph/tool loop (P10), frontend, persistence.

ACCEPTANCE: invalid model outputs never reach the response; fallback report works without the LLM; offline tests green; live call reported honestly or marked "not run".
VERIFY: `uv run pytest tests/test_llm*.py tests/test_report*.py`, full suite, ruff, gated live script.
RISKS: rate limits/credits; model refusing the schema; keep live calls minimal.
DOCS: docs/LLM_PROVIDER_NOTES.md, IMPLEMENTATION_STATUS, KNOWN_ISSUES (KI-25).
Finish with the AGENTS.md section 12 report.
```

## P10 — Bounded agent workflow (LangGraph or fixed pipeline per verified capabilities)

```
Read AGENTS.md; docs/LLM_PROVIDER_NOTES.md; the llm/, recommend/, rag/ and bundle code from P05-P09; docs/handoff/PROJECT_CONTEXT.md section 6.

OBJECTIVE
Orchestrate environmental analysis, retrieval, recommendation ranking and report drafting in a bounded, auditable workflow. The LLM coordinates and explains; deterministic code computes and enforces.

PREREQUISITES: P09 done. Verify current LangGraph documentation/version before use and record it. If P03 showed the model cannot call tools reliably, implement a FIXED sequential pipeline where the LLM only drafts the narrative; document the decision.

WORK
1. Tools (thin wrappers over deterministic functions with Pydantic inputs/outputs): get_environmental_bundle, retrieve_evidence (hybrid or BM25 if dense unavailable), rank_adaptation_options, validate_report. The LLM has no filesystem or arbitrary network access.
2. Workflow: validate inputs -> environmental bundle -> retrieval -> ranking -> draft (LLM) -> validate -> finalize or deterministic fallback. Hard limits: max steps, max tool calls, token budget, per-call and total timeouts, loop detection.
3. Tracing: persist an auditable trace (tool inputs/outputs, versions, timings, validator verdicts) without secrets.
4. Failure policy: any tool failure or invalid draft produces a clearly labelled partial or fallback report; never fabricate missing values.
5. Tests with FakeProvider: happy path; limit enforcement; tool failure injection; validator rejection; trace completeness; no network. One gated live end-to-end run for the reference scenario (report time, calls, usage).

OUT OF SCOPE: persistence/history (P11), UI, new indicators or catalog entries.

ACCEPTANCE: bounded execution proven by tests; every report passes the P09 validator or is the labelled fallback; traces generated.
VERIFY: `uv run pytest tests/test_agent*.py`, full suite, ruff, gated `uv run python scripts/run_agent.py ...` (create the script).
RISKS: infinite loops, token blow-up, rate limits, hidden nondeterminism; log seeds/temperature if configurable.
DOCS: docs/AGENT_WORKFLOW.md, IMPLEMENTATION_STATUS, KNOWN_ISSUES.
Finish with the AGENTS.md section 12 report.
```

## P11 — Scenario API, persistence, and frontend contract

```
Read AGENTS.md section 10; src/climateadapt/api/*; the agent and job code (P05, P10); docs/handoff/KNOWN_ISSUES.md KI-28, KI-29.

OBJECTIVE
Provide the API the React app needs: create a scenario, track its job, retrieve results, list history. Persist inputs, deterministic outputs, trace and report.

PREREQUISITES: P10 done.

WORK
1. Endpoints: POST /v1/scenarios (validate, enqueue agent run, return 202 + ids), GET /v1/scenarios, GET /v1/scenarios/{id}, reuse GET /v1/jobs/{id}. Responses separate deterministic results, evidence, recommendations, report, limitations and provenance. Add retrieval endpoints only if the UI needs them (POST /v1/evidence/search with citations).
2. Persistence: SQLite via the standard library or a lightweight, verified dependency; schema + minimal migration approach; store inputs, bundle JSON, report JSON, trace, status, timestamps. (PostgreSQL only if the owner asks; keep the storage layer swappable.)
3. Stable error contract (same shape), pagination for history, deletion of a scenario, request-size limits.
4. Export OpenAPI to docs/openapi.json and note how the frontend should consume it.
5. Tests: lifecycle, persistence across app restarts (temp DB), failed runs stored with errors, validation errors, history pagination, CORS.

OUT OF SCOPE: frontend code, authentication (document the lack of auth as a limitation), PostGIS.

ACCEPTANCE: a scenario can be created, polled, retrieved and listed; stored data matches what the frontend needs; tests green.
VERIFY: `uv run pytest`, `uv run ruff check .`, manual calls with the PowerShell examples documented in README.
RISKS: schema drift after the frontend starts; version the response models.
DOCS: README API section, docs/openapi.json, IMPLEMENTATION_STATUS.
Finish with the AGENTS.md section 12 report.
```

## P12 — React + Vite frontend scaffold and environmental analysis views

```
Read AGENTS.md section 10; docs/openapi.json; docs/handoff/PROJECT_CONTEXT.md. The repository has no frontend yet. Do NOT use Streamlit.

OBJECTIVE
Create the React + Vite application and the input/analysis screens that call the FastAPI backend.

PREREQUISITES: P05 stable (P11 preferred; otherwise mock the scenario endpoints). Node.js and npm installed (verify versions and record them).

WORK
1. frontend/ with Vite + React + TypeScript (strict), ESLint, Vitest + Testing Library. Verify each tool's current documentation before use; do not guess commands. Environment: VITE_API_BASE_URL (public value only). Dev server on a documented port that matches the backend CORS setting.
2. Typed API client derived from docs/openapi.json (generated or hand-written with a contract test).
3. Screens: scenario form (latitude/longitude with validation and coverage hints, target end month, timescale, reference period, crop, water-access flags, optional ERA5 land-fallback toggle with explanation), job progress/polling, results page with one card per indicator (value, units, reference period, data source and coverage, status, limitations, provenance, warnings such as fallback grid point or cell-edge flag), and a simple chart of reference-year totals vs the target. Map the API error `type` codes to specific messages.
4. Never render a composite score or severity label. Show percentage anomaly only with its caveat and always alongside the reference period.
5. Tests: component tests (loading, error codes, partial failure, fallback warning), client contract test, lint and build.

OUT OF SCOPE: recommendations/report UI (P13), authentication, mobile polish.

ACCEPTANCE: `npm run build`, `npm run lint`, `npm run test` pass (report counts); the app runs against the real backend and shows the reference scenario with warm caches; screenshots or a text description of the verified behavior.
VERIFY: `cd frontend; npm install; npm run lint; npm run test; npm run build; npm run dev` plus `uv run uvicorn climateadapt.api.main:app --reload`.
RISKS: CORS/port mismatch; long cold requests (show progress and timeouts); map library choice (verify docs; a lat/lon form is acceptable first).
DOCS: README frontend section, IMPLEMENTATION_STATUS (frontend now exists), remove stale Streamlit mentions.
Finish with the AGENTS.md section 12 report.
```

## P13 — Recommendations, evidence-linked report, and history in the UI

```
Read AGENTS.md sections 7 and 10; docs/openapi.json; the report schema (P09); the frontend code from P12.

OBJECTIVE
Present ranked options and the cited report so that every claim is traceable, uncertainty is visible, and AI-written text is clearly separated from deterministic results.

PREREQUISITES: P11 and P12 done.

WORK
1. Report page: sections from the report schema. Each claim shows linked evidence (title, authors, year, PDF page and printed page when available, landing URL, licence note, "metadata unverified" flag from the manifest).
2. Recommendation panel: ranked options with the score component breakdown, eligible vs excluded options with reasons, explicit "unknown" values (never blank or zero), evidence strength.
3. Labels: "AI-generated narrative" vs "Computed by the platform"; a fallback banner when the report is the deterministic fallback; a limitations section always visible; data-coverage statement.
4. Scenario history list with open/delete, status badges, and failure details.
5. Export the report as Markdown (include citations and limitations).
6. Tests: components for evidence links, unknown handling, fallback banner, excluded options; snapshot tests only where stable; lint and build.

OUT OF SCOPE: new backend capability, authentication, collaboration features.

ACCEPTANCE: from a created scenario the user can reach a cited report and inspect each claim's evidence; unknowns and limitations are visible; tests/build green.
VERIFY: `cd frontend; npm run lint; npm run test; npm run build` plus a manual run (report what you saw).
RISKS: long text layout; accidentally displaying model-written numbers as authoritative.
DOCS: README, IMPLEMENTATION_STATUS.
Finish with the AGENTS.md section 12 report.
```

## P14 — End-to-end tests, demo mode, and multi-location real runs

```
Read AGENTS.md; the full API/agent/frontend code; docs/handoff/KNOWN_ISSUES.md KI-14.

OBJECTIVE
Make the whole application reproducibly demoable and test it end to end, while staying honest about how far it was verified geographically.

PREREQUISITES: P13 done; caches warm for demo locations; limited live LLM budget agreed with the owner.

WORK
1. Backend integration tests across the complete workflow with fakes (no network). Frontend end-to-end test with a verified tool (check Playwright or alternative docs; record the version) against a mocked backend.
2. Demo mode (e.g., CLIMATEADAPT_DEMO_MODE): serve stored results from real cached runs, clearly labelled "cached real-data snapshot" with timestamps; works offline and when rate limits are hit. Store snapshots under a git-ignored path with a documented regeneration command.
3. Real-data runs at 3-4 contrasting locations: the reference point (30.43, -9.61); one in CHIRPS coverage outside Africa; one north of 60N (CHIRPS must report outside_coverage while ERA5-Land works); one ocean/masked point (must report missing/fallback behavior). Record outputs and failures in docs/DEMO_RUNS.md without claiming validation.
4. A demo script (docs/DEMO_SCRIPT.md): exact steps, expected screens, fallback plan if the model or CDS is unavailable.

OUT OF SCOPE: new features, performance tuning beyond fixing blockers.

ACCEPTANCE: e2e tests green; demo mode verified offline; DEMO_RUNS.md has real results; known failure modes documented.
VERIFY: `uv run pytest`, `uv run ruff check .`, `cd frontend; npm run test; npm run build`, the e2e command, a manual demo walk-through.
RISKS: live CDS/Baseten flakiness; keep live calls minimal and counted.
DOCS: README demo section, IMPLEMENTATION_STATUS, KNOWN_ISSUES (KI-14).
Finish with the AGENTS.md section 12 report.
```

## P15 — Essential MLOps: Docker, Compose, CI (+ thin real extras only if approved)

```
Read AGENTS.md; pyproject.toml; docs/handoff/KNOWN_ISSUES.md KI-30; docs/handoff/PROJECT_CONTEXT.md section 5.

OBJECTIVE
Make the project reproducible and automatically tested. Add other named MLOps tools only as small integrations that genuinely run and are demonstrated.

PREREQUISITES: P13/P14 done. Docker installed (verify). Ask the owner which extras (Prometheus, MLflow, Optuna, Evidently, Airflow, Grafana, PostgreSQL) are worth doing given the rubric and time.

WORK (core)
1. Dockerfiles for backend and frontend (check the Python image and GDAL/rasterio wheel behavior; keep images reasonable), .dockerignore (exclude data/, .env, corpus), docker-compose with health checks, environment via env files (no secrets in images), volumes for data/cache.
2. CI: .github/workflows/ci.yml running ruff, pytest (offline), frontend lint/test/build, dependency caching. Never use live APIs or secrets in CI.
3. Document `docker compose up` usage. Report whether you actually ran it.

WORK (extras, only if approved and only if actually run)
- Prometheus: /metrics endpoint (verify prometheus-client docs) with request/job/LLM-call counters; scrape config.
- MLflow + Optuna: log retrieval evaluation runs and an Optuna search over BM25/RRF/chunk parameters on the reviewed gold set (small, exploratory, with overfitting caveat).
- Evidently: data-quality/drift report on indicator inputs.
- Each extra needs a one-command demo and recorded output. Anything not run is listed as NOT IMPLEMENTED.

OUT OF SCOPE: Kubernetes, cloud deployment, Airflow/Grafana/PostGIS unless explicitly approved.

ACCEPTANCE: image builds and containers start (report output); CI workflow present and valid (state clearly whether it has executed on GitHub); extras documented with evidence or listed as not done.
VERIFY: `docker compose build`, `docker compose up`, health-check calls, local `uv run pytest`; CI status screenshot/log only if run.
RISKS: large images, GDAL wheels, Windows/WSL differences, secrets leakage via build context.
DOCS: README run instructions, IMPLEMENTATION_STATUS MLOps table, KNOWN_ISSUES (KI-30).
Finish with the AGENTS.md section 12 report.
```

## P16 — OPTIONAL: CropHarvest computer-vision baseline (only on owner "go")

```
Read AGENTS.md; docs/handoff/KNOWN_ISSUES.md KI-31. Proceed ONLY if the owner has explicitly said yes.

OBJECTIVE
Establish a defensible, evaluated baseline on a well-defined crop/non-crop (or similar) task with CropHarvest, tracked with MLflow. This supports the project's technical depth; it must never be presented as evidence of drought damage or of intervention effectiveness.

PREREQUISITES: owner go decision; P15 MLflow set up if tracking is wanted; GPU/CPU capability and disk budget confirmed. Verify current CropHarvest, PyTorch and timm documentation before use; record versions.

WORK
1. Define the target, splits (document the leakage controls, prefer geographic/group splits), metrics and a simple classical baseline first (e.g., logistic regression/random forest on aggregated features), then a small neural model only if justified.
2. Reproducible training script, seeds, evaluation report with per-class metrics and confidence intervals where feasible, and MLflow tracking (verify it actually runs).
3. Optuna only after the baseline and evaluation protocol are fixed.
4. Document dataset coverage and licence, and what the model can and cannot support.

OUT OF SCOPE: yield/drought-damage prediction, integration into recommendations, large-scale training.

ACCEPTANCE: documented metrics from an actual run; honest limitations; offline unit tests for data handling; no performance claim without a stored result.
VERIFY: training script run output, MLflow run id, `uv run pytest`, `uv run ruff check .`.
RISKS: dataset download size, compute, time sink. Stop if it threatens Tier A tasks.
DOCS: docs/VISION_BASELINE.md, IMPLEMENTATION_STATUS.
Finish with the AGENTS.md section 12 report.
```

## P17 — Final documentation, security review, and submission packaging

```
Read AGENTS.md and all docs/handoff/*.md; the real repository state.

OBJECTIVE
Leave an accurate, reproducible, safe-to-share project: documentation matches code, no secrets or restricted content are shipped, and the demo is documented.

PREREQUISITES: P14 done; P15 done or explicitly skipped.

WORK
1. Reconcile every handoff document with the actual repository; mark each item CONFIRMED / REPORTED / UNVERIFIED with fresh evidence, and delete obsolete statements (including Streamlit mentions).
2. README: setup, configuration, commands, scientific scope and limitations, data sources and licences, model access instructions (no secrets), demo steps, testing.
3. Security review: scan tracked files and git history for secrets; confirm .gitignore covers .env, data/, corpus text; check logs/responses for secret or local-path leakage; confirm no real credentials in fixtures or docs; list dependencies' licences if feasible.
4. Licence/citation check: CHIRPS and ERA5-Land attributions, corpus licences, "metadata unverified" items; make sure no PDF/extracted text is in any submission artifact.
5. Final full verification: `uv sync --extra dev`, `uv run pytest`, `uv run ruff check .`, frontend lint/test/build, Docker build if present. Record exact results in docs/FINAL_VERIFICATION.md.
6. docs/SUBMISSION_CHECKLIST.md: what is implemented, what is not, known limitations, how to run the demo, how model access is configured.

OUT OF SCOPE: new features.

ACCEPTANCE: documentation matches the code; verification results recorded with dates and counts; no secrets/corpus text in the repo or artifacts.
RISKS: stale claims; incomplete history scan. State what could not be checked.
Finish with the AGENTS.md section 12 report.
```
