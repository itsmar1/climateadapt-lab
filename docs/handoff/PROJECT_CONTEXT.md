# ClimateAdapt Lab — Project Context

Handoff date: 2026-10-28. Written by Claude (browser chat) from conversation history. **No repository access was available**; the only project file visible was `technical_blueprint.txt` (the original architecture blueprint). Status labels follow `AGENTS.md`: CONFIRMED / REPORTED / UNVERIFIED.

## 1. Vision

An evidence-grounded agricultural drought-adaptation platform that lets a user investigate drought conditions and compare adaptation strategies using environmental observations, retrieved scientific literature and a controlled AI-agent workflow. It is meant to extend the owner's earlier irrigation-management work (ECO DRIP, 2023) from managing irrigation requirements toward evaluating a broader set of drought-adaptation decisions (source: blueprint).

**Central principle.** Scientific calculations and recommendation constraints stay in tested Python. The LLM coordinates tools, synthesizes retrieved evidence and writes explanations. It never computes authoritative numbers, never overrides hard constraints, and never invents citations or benefits.

**Scope rule (blueprint).** Global coverage belongs in the *architecture*; global *validation* must be demonstrated incrementally. Each data source and recommendation category must state where it is supported and what evidence backs it.

## 2. Target users (INFERRED — please confirm)

The blueprint says "users" without defining them. Reasonable inference from the product: agronomists and extension officers, farm-advisory and NGO programme staff, regional planners, and researchers who need defensible, cited drought context and option comparisons. Not farmers acting without an advisor, and not an automated emergency-declaration system. **Owner: confirm or replace this list.**

## 3. Judging criteria and hackathon rules — NOT PROVIDED

The official judging rubric, deadline, submission format and rules about pre-built work were **not supplied** in any file or message. The blueprint itself says the official rules should determine what may be prepared in advance. Do not invent them.

Provisional proxies used by the roadmap (assumptions, to be replaced by the real rubric):

| Proxy criterion | What would demonstrate it |
|---|---|
| Technical depth and correctness | Tested indicators, provenance, evaluated retrieval |
| Working end-to-end demo | One scenario from input to cited report in the UI |
| Meaningful use of Meta's model | Agent tool orchestration + schema-validated report via Muse Spark |
| Trust / scientific integrity | Citation verification, explicit uncertainty, no fabricated numbers |
| Real-world relevance | Concrete drought-adaptation decision support |
| Engineering practice | Tests, CI, Docker, documentation |
| Presentation | Clear limitations, reproducible demo |

**Owner to provide:** official rubric and weights, deadline, team/submission rules, any "prebuilt components" restrictions.

## 4. Model access and constraints

- Application inference: Baseten model **`meta-models/muse-spark-open-1026`**, with credits and rate-limit restrictions (stated by owner; REPORTED).
- **P03 verified 2026-10-30 (see `docs/LLM_PROVIDER_NOTES.md`):** endpoint `https://inference.baseten.co/v1/chat/completions` (OpenAI-compatible), `Authorization: Bearer` auth, `-1026` slug, and tool-call round trip all work live; structured output is *not enforced* for this model (docs) so P09 must validate client-side. No LLM integration code exists in the repo yet (settings + gated smoke script only). Do not assume another model ID or provider is available.
- **Still UNVERIFIED:** numeric rate/context/output limits for this model, credit balance/budget; live behavior beyond the 5-call smoke run.
- The blueprint's "Meta Model API" wording is superseded by the Baseten route above. The blueprint's risk table already requires isolating model calls behind a provider adapter; keep that.
- Credentials: Muse Code's own login/auth and the application's Baseten key are different things. The app key lives in environment configuration only.
- Design for graceful degradation: if the model is unavailable or rate-limited, deterministic outputs (indicators, retrieval, ranking) must still be viewable, clearly marked as having no AI narrative.

## 5. Technology decisions (current)

| Area | Decision | Status |
|---|---|---|
| Language/tooling | Python 3.11, `uv`, pytest, ruff | Implemented, CONFIRMED running on owner's Windows machine (Python 3.11.17, pytest 9.1.1) |
| Backend | FastAPI + Pydantic v2 | Implemented (4 routes) |
| Frontend | **React + Vite** (supersedes blueprint's Streamlit/Plotly) | Input/analysis screens delivered (P12 2026-10-31; 42 tests green); recommendations/report UI is P13 |
| Rainfall data | CHIRPS v3 Final monthly, 0.05°, 60°S–60°N, 1981→ | Implemented, real-data CONFIRMED |
| Climate data | ERA5-Land monthly means via Copernicus CDS, 0.1° grid, 1950→ | Implemented, real-data CONFIRMED (tp, t2m, swvl1) |
| Indicators | Percentage anomaly (prototype), SPI (gamma, Thom fit), temperature window anomaly, SPI fit diagnostics | Implemented, real-data CONFIRMED |
| RAG | BM25 + RRF implemented; **dense retrieval (multilingual-E5 + Qdrant) planned** | Partial |
| Embeddings | `intfloat/multilingual-e5-*` (small=118M/384-d, base=278M, large=560M; blueprint named large; small preferred for CPU laptops, configurable). Requires `query: `/`passage: ` prefixes | Planned, UNVERIFIED in this repo |
| Vector DB | Qdrant client local mode (in-memory or path, no server) | Planned; local-mode support verified from docs, not exercised |
| Agent | LangGraph bounded workflow, tools named in blueprint | Not started |
| Recommendation | Structured intervention catalog + deterministic constraints/ranking | Not started |
| Computer vision | PyTorch/timm on CropHarvest crop/non-crop | Not started; deferred (decision pending) |
| Persistence | Blueprint: PostgreSQL/PostGIS | Not started |
| MLOps tools named by owner | MLflow, Pytest, Optuna, CI/CD, Docker, FastAPI, Airflow, PostgreSQL, Prometheus, Evidently, Grafana | Only Pytest and FastAPI exist (2 of 11) |

## 6. Intended architecture (target)

Seven layers from the blueprint, with overrides: (1) UI — **React + Vite**; (2) data ingestion/geospatial; (3) environmental analysis (+ optional vision); (4) scientific RAG; (5) adaptation recommendation engine; (6) agent orchestration + API; (7) persistence/evaluation/MLOps.

Agent tools (blueprint names): `get_environmental_summary`, `get_vegetation_analysis`, `retrieve_agricultural_evidence`, `get_crop_context`, `rank_adaptation_options`, `validate_recommendation`. A final validator must check that citations match retrieved sources, required fields exist, assumptions are explicit and unsupported efficacy claims are excluded.

Blueprint MVP ("must work reliably"): location and coverage validation; CHIRPS + ERA5-Land analysis; one well-defined remote-sensing experiment; curated RAG with verified citations; transparent ranking engine; Muse Spark tool orchestration with structured report; FastAPI, PostgreSQL, Docker, Pytest, CI/CD, experiment tracking; basic Airflow and monitoring. Blueprint stretch: WaPOR, SAM 3.1, more languages/crops, cross-region evaluation, broader sensors. **Because time is limited, the roadmap proposes a thinner MVP; see `IMPLEMENTATION_ROADMAP.md`.**

## 7. What is implemented vs. planned (summary)

Implemented (details and evidence in `IMPLEMENTATION_STATUS.md`): configuration; CHIRPS and ERA5-Land point connectors with caching, provenance, coverage checks; precipitation anomaly, SPI, temperature anomaly and SPI diagnostics; three CHIRPS-based API endpoints plus health; CLI scripts; a curated source manifest, PDF fetch/ingest/chunk, BM25, RRF, citations and an evaluation harness (4 of 8 documents ingested).

Planned / not built: dense retrieval; soil-moisture anomaly; ERA5 API endpoints; recommendation engine and intervention catalog; LLM provider adapter and agent; scenario persistence; React frontend; Docker/CI and the remaining MLOps tools; computer vision; Sentinel-2/WaPOR/SAM.

## 8. Decisions that changed since the blueprint

1. Frontend: Streamlit → **React + Vite** (owner requirement).
2. Model route: "Meta Model API" → **Baseten** `meta-models/muse-spark-open-1026` (owner statement; unverified API details).
3. Milestone order: computer vision (M3) deferred; scientific RAG built first because the recommendation engine and agent depend on retrieval, not on CV.
4. Embedding model: default proposed as `multilingual-e5-small` (CPU practicality) instead of `-large`; configurable.
5. Retrieval: BM25 and RRF implemented by hand (small, tested) instead of a library.

## 9. Reference data and findings (real runs, CONFIRMED from owner's logs)

Reference point used in every real run: lat 30.43, lon −9.61 (chosen so it is not on a CHIRPS cell edge). Jan–Mar 2024:

- CHIRPS total 76.87 mm. Percentage anomaly vs 2011–2020: +0.55 %. SPI-3 vs 1991–2020: −0.517 (P=0.303); empirical-rank SPI −0.341; KS D=0.093.
- ERA5-Land (neighbour grid point (30.5, −9.6), 7.8 km away because (30.4, −9.6) is masked): total 59.15 mm, SPI-3 −0.375; yearly-total correlation with CHIRPS 0.77; monthly shapes differ strongly.
- ERA5-Land temperature anomaly +2.22 °C (z +2.55, warmest of 30 reference winters). Soil water layer 1: 0.070, 0.110, 0.112 m³/m³ (not interpreted: absolute ERA5-Land soil water has documented bias elsewhere).
- Interpretation limits: one point, one season, no ground truth; the CHIRPS/ERA5 long-term differences are within sampling noise on this evidence. Do not present these as general findings.

## 10. Reuse and licensing notes

CHIRPS data: public domain/CC BY 4.0 per CHC (cite DOI 10.15780/G2JQ0P). ERA5-Land: Copernicus licence; acknowledge "Copernicus Climate Change Service Information". Corpus documents have mixed licences (FAO notices, CC-BY-NC-ND, CC-BY-SA; several UNVERIFIED) — keep processed text local and cite originals.
