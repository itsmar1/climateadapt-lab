# Muse Spark evidence (P25) — one accepted run, honestly reported

Model: **`meta-models/muse-spark-open-1026`** via Baseten Model APIs
(`POST https://inference.baseten.co/v1/chat/completions`, Bearer key).
Tool calling was verified live in P03 (one round trip; see
`docs/LLM_PROVIDER_NOTES.md`); structured output is *not enforced* for this
model, so every draft is validated client-side by deterministic code.
This page reports one saved run; it claims nothing about other runs.

## How a report is produced

1. Deterministic Python computes the environmental bundle (CHIRPS + ERA5-Land
   indicators), retrieves cited passages (BM25), and ranks adaptation options
   (hard constraints + transparent scores). The model computes nothing.
2. The model drafts the report narrative (one call, `max_tokens=16000`).
3. Deterministic code validates every statement: schema, known ids, citations
   rebuilt verbatim, every numeral traced to a registry value, mandatory
   limitations/provenance, bans on severity labels, efficacy claims, and
   currency/percent. Anything failing is rejected.
4. At most one repair turn (same prompt + the validator's problems), validated
   identically. Since P23 the shipped report keeps every valid model
   statement and replaces each failing one with the deterministic fallback's
   counterpart (dropped when unsafe), then re-validates the whole report.
5. If nothing validates, the labelled deterministic fallback ships instead —
   a run can always end in fallback, and fallback is a normal outcome.

## The accepted run (CONFIRMED from saved files)

Files (git-ignored): `data/agent_runs/run-20261102T202227Z.json` and
`-trace.json`. Reference scenario: 30.43, -9.61, window ending 2024-03,
3-month timescale, reference 1991–2020. Served as tracked snapshot
`reference-morocco-ai` (see `demo/README.md`).

- Outcome: `complete`, zero problems. Report `ai-accepted`: **14/14
  statements model-written (validated)**, `fallback=false`.
- Model calls: **2** (1 draft + 1 repair). Tokens: **prompt 61,385 /
  completion 23,296** (trace `usage` totals).
- Latency: **101,781 ms** total; draft 58,594 ms, validate 24,890 ms
  (includes the repair call), bundle 16,547 ms, retrieval 1,750 ms.
- First draft: rejected with 1 problem, **`invalid-json`** — truncated at
  the 16,000-token completion cap (`finish_reason=length`, unterminated
  string at char 5239). The repair was accepted (`[repair-accepted]`).
- The model uses many tokens: ~61k prompt tokens for one scenario, and the
  first draft still hit the output cap. Budget accordingly.

## What is NOT claimed

- No benefit, cost, or effectiveness figure is invented: the catalog echoes
  `unknown` unless a cited source states a value, and the validator rejects
  anything else.
- No live-rate, credit-balance, or price figure is stated here; numeric
  rate/context limits remain UNVERIFIED (KI-25).
- One accepted run does not prove the next run will accept; fallback
  remains the honest default whenever validation fails.
