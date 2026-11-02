# Submission packet (P21 draft — owner fills the bracketed parts)

## Project title

ClimateAdapt Lab — Evidence-Grounded Agricultural Drought Adaptation

## One-paragraph description

ClimateAdapt Lab helps agronomists and planners compare drought-adaptation
options for a specific place and season. For one location it computes
environmental indicators from CHIRPS and ERA5-Land (with provenance, units,
reference periods, and limitations on every value), retrieves cited
scientific evidence, ranks interventions with deterministic, fully explained
rules — and has Meta's Muse Spark model draft the final report, which is
then validated against the schema, the citations, and the computed numbers
before anyone sees it. Rejected drafts become a clearly labelled
deterministic fallback, never silent fiction: no severity scores, no
invented benefits, no imputed missing values. A React UI with an interactive
map carries the whole flow from location pick to citable Markdown export,
and a zero-key demo mode replays audited real-data snapshots offline.

## Track / problem-statement mapping

[OWNER: fill in — the official rubric, tracks, and problem statements were
never provided (KI-32). Provisional mapping: end-to-end AI agent demo with
meaningful Muse Spark use (draft + validation loop), scientific-integrity
engineering (provenance, validators, explicit unknowns), and real-world
relevance (drought-adaptation decisions for advisory and planning users).]

## Links list

- Repository: [OWNER: paste the submission repo URL]
- Demo video (3 min): [OWNER: paste the video URL after recording —
  script in `docs/DEMO_SCRIPT.md`]
- Live demo / hosted app: none — local + compose only (no hosted
  deployment); judges run the zero-key quickstart in `README.md`
- Key docs in-repo: `README.md` (quickstart), `docs/DEMO_RUNS.md` (real
  outputs), `docs/LLM_PROVIDER_NOTES.md` (model verification),
  `docs/AGENT_WORKFLOW.md` (agent design), `docs/FINAL_VERIFICATION.md`
  (evidence), `docs/SUBMISSION_CHECKLIST.md` (scope + limits)
- Model: `meta-models/muse-spark-open-1026` via Baseten Model APIs
  (key required only for live drafts; fallback spends $0)
