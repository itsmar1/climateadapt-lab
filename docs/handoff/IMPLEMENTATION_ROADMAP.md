# Implementation Roadmap

Handoff date: 2026-10-28. Task IDs (P00…P17) refer to `MUSE_CODE_TASK_PROMPTS.md`. This roadmap rests on `IMPLEMENTATION_STATUS.md` and `KNOWN_ISSUES.md`, which were written without repository access: **confirm with the P00 audit before relying on it.**

## 1. Planning assumptions (replace when known)

- **Deadline and judging rubric are unknown.** Sizes below are relative: **S** ≈ a few hours, **M** ≈ about a day, **L** ≈ multiple days of focused work. Convert to dates once the deadline is supplied.
- Provisional value proxies (see `PROJECT_CONTEXT.md` §3): technical rigor, a working end-to-end demo, meaningful use of Meta's model, scientific trust, real-world relevance, engineering practice, presentation.
- Environmental layer (Milestones 1–2) is substantial and real-data-verified. The two largest gaps are the **application layer** (recommendations, agent, frontend) and the **verified baseline**.
- Every task is reviewable on its own and ends with test results actually run (see `AGENTS.md`).

## 2. Where the repository changes the requested order

The requested priority order is kept, with these evidence-based adjustments:

1. **Baseten verification spike (P03) moves early, in parallel with environmental work.** Whether Muse Spark on Baseten supports tool calling and schema-constrained output decides the agent design (P09–P10). It is the largest unknown (KI-25) and costs little to check with a tiny gated script. The adapter and agent still come after retrieval and recommendations.
2. **RAG hardening before dense retrieval.** Page labels, document completeness and a reviewed gold set (P06) make the later dense/hybrid comparison meaningful. Dense retrieval on an unreviewed 8-query set would prove nothing.
3. **Recommendation catalog is gated by corpus coverage** (KI-26). The corpus currently supports irrigation-related options; the owner must supply or approve additional sources before the catalog can honestly include other options.
4. **Frontend scaffolding can start once the analysis API is stable (after P05)** using the OpenAPI contract and mocked report data, so UI work runs in parallel with RAG/agent work. The evidence-linked report view (P13) waits for P11.
5. **Computer vision (M3) was optional (P16) — delivered 2026-11-01** (classical baseline; neural + Optuna deferred). It blocked nothing.
6. **MLOps is thin by design.** Docker and CI come first; other named tools only as small integrations that actually run.

## 3. Phased plan

| Phase | Tasks | Size | Depends on | Outcome |
|---|---|---|---|---|
| 0. Baseline | P00 audit (read-only) → P01 fix verified problems | S+S | owner pastes nothing new | Verified, green suite and ruff; audit report |
| 1. Uncertainties | P02 units/CDS verification; P03 Baseten spike | S+M | P01 (P03 can start after P00) | `swvl1` units recorded; real CDS retry behavior known; verified Baseten capabilities and limits |
| 2. Environmental completion | P04 soil-moisture anomaly + shared helper; P05 environmental API (ERA5, jobs, CORS, analysis bundle) | M+L | P02 | Complete indicator set behind a stable, non-blocking API; analysis "evidence bundle" contract |
| 3. Scientific RAG | P06 hardening (page labels, completeness, reviewed gold set); P07 dense + hybrid + evaluation | M+L | owner supplies PDFs; P01 | Measured retrieval quality with correct citations |
| 4. Recommendations | P08 catalog + constraints + ranking | L | P06/P07; owner-approved sources; P05 bundle | Deterministic, evidence-linked ranking with explicit unknowns |
| 5. Model + agent | P09 provider adapter, report schema, citation validator; P10 bounded agent | L+L | P03, P05, P08 | Schema-valid, citation-verified reports via Muse Spark with deterministic fallback |
| 6. Application | P11 scenario API/persistence/contract; P12 React+Vite scaffold + analysis views; P13 recommendations + report + history | M+L+L | P05 (P12 start), P10/P11 (P13) | Usable UI from input to cited report |
| 7. Demo quality | P14 E2E tests, demo mode, multi-location real runs | M | P13 | Reproducible demo; honest cross-location behavior |
| 8. MLOps essentials | P15 Docker + Compose + CI (+ thin real extras) | M | P11–P13 | One-command run; automated tests |
| Optional | P16 CropHarvest vision baseline | L | owner go decision | ✅ Done 2026-11-01 (classical; see VISION_BASELINE.md) |
| Close | P17 docs, security review, submission packaging | S–M | all | Accurate docs; no secrets/corpus text in artifacts |

## 4. Scope tiers (decide cut lines with the owner)

- **Tier A — minimum credible demo (must-have):** P00, P01, P02, P03, P05 (CHIRPS + ERA5 endpoints), P06, P08 (small catalog), P09, P10, P11, P12, P13, P15 (Docker + CI). Delivers: location/season/crop → environmental evidence → cited retrieval → ranked options → Muse Spark report in a React UI, with tests.
- **Tier B — strengthen (should-have):** P04 (soil moisture), P07 (dense + hybrid), P14 (multi-location runs, E2E), PostgreSQL for history, `/metrics` for Prometheus.
- **Tier C — differentiators (only if time and rubric reward them):** MLflow/Optuna on retrieval evaluation, Evidently data-drift check, Airflow cache-warming DAG, Grafana dashboard, ~~P16 vision baseline~~ (✅ done 2026-11-01).
- **Not planned:** area/polygon analysis, WaPOR, SAM/Sentinel-2 pipelines, additional languages beyond evaluated ones, mobile app. Revisit only with an explicit owner decision.

If time collapses, protect in this order: verified baseline → honest indicators → cited retrieval → ranked options with explicit unknowns → working UI → Docker/CI. A smaller, correct, fully verified system beats a broad one with unverified claims.

## 5. Parallel work

- After P01: P02 and P03 are independent.
- After P05 is stable: P12 (frontend scaffold) in parallel with P06/P07 (RAG).
- P08's catalog design can begin while P07 runs, but its evidence links need P06/P07 output.
- Owner actions run in parallel with all of it: PDFs, rubric, Baseten details, reviewing gold labels and catalog sources.

## 6. Checkpoints that need the owner

1. After P00: confirm audit findings and approve P01 scope.
2. Before P06: provide the 3 manual PDFs (and WMO retry/mirror).
3. Before P08: approve adaptation-option sources and the catalog scope.
4. After P03: decide the agent design (tool calling vs fixed pipeline) from verified capabilities.
5. ~~Before P15/P16: decide which MLOps extras and whether to include vision.~~ Decided 2026-11-01: P15 core-only; P16 approved and delivered.

## 7. Top risks

| Risk | Mitigation |
|---|---|
| Baseten rate limits/credits exhausted during build or demo | Tiny gated smoke tests; fake provider in tests; deterministic fallback; cache/demo mode |
| Model lacks tool calling/structured output | Verified in P03; design a fixed, validated workflow where the LLM only writes explanation |
| Hallucinated citations or numbers | Citation validator (P09); numbers only from deterministic tool outputs; reject unsupported claims |
| CDS/CHIRPS latency or throttling during demo | Job pattern (P05), warm caches, offline demo mode (P14) |
| Corpus too narrow for credible recommendations | Owner-approved additional sources before P08; unknowns explicit |
| Scope creep | Tiers above; do not add features without a rubric-based reason |
