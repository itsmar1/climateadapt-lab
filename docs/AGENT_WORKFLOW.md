# Agent Workflow (P10) — Fixed Sequential Pipeline

## 1. Architecture decision: fixed pipeline, no LangGraph (recorded 2026-10-31)

LangGraph was checked before use, as required: **PyPI `langgraph` 1.2.19**
(primary source, `https://pypi.org/pypi/langgraph/json`, fetched 2026-10-31;
docs at `https://docs.langchain.com/oss/python/langgraph/overview`). It was
deliberately **not adopted**:

1. The workflow is inherently linear — validate → bundle → retrieve → rank →
   draft → validate → finalize. No branching or replanning need exists that a
   graph would serve; a fixed order is easier to bound, trace, and test.
2. P03 verified tool-calling on **one trivial probe only** (`add(3.14, 3.14)`),
   not multi-step planning or loops. A ReAct-style loop on this reasoning
   model would multiply the token blow-up already observed (P09: a full
   4000-token budget consumed with zero content; P10 live run below: 15087
   completion tokens for one draft).
3. No server-side schema enforcement exists for this model, so the P09
   validator is the enforcement point. A fixed pipeline guarantees every
   report passes it or is the labelled fallback, with no loop or escape path.
4. No new heavy dependency; deterministic Python coordinates *and* enforces,
   which is a stronger guarantee than AGENTS.md §1's minimum ("the LLM only
   coordinates tools and explains").

Revisit only if a future workflow genuinely needs branching (multi-scenario
comparison, clarification loops) AND tool-calling proves reliable over long
contexts. Blueprint tool names (`get_environmental_summary`,
`get_vegetation_analysis`, `retrieve_agricultural_evidence`, `get_crop_context`,
`rank_adaptation_options`, `validate_recommendation`) map to the four tools in
§2; vegetation and crop-context tools do not exist (no such indicators yet).

## 2. Tools (`src/climateadapt/agent/tools.py`)

Thin typed wrappers over deterministic functions (Pydantic in, Pydantic out).
The LLM never calls them and has no filesystem or network access beyond the
single draft completion.

| Tool | Wraps | Notes |
|---|---|---|
| `get_environmental_bundle` | P05 `run_environmental_bundle` | Per-indicator statuses; failures reported, never hidden |
| `retrieve_evidence` | BM25, or RRF hybrid when a dense retriever is injected | Live path uses BM25 (offline, no model download) |
| `rank_adaptation_options` | P08 `recommend` | Deterministic constraints + ranking |
| `validate_report` | P09 `validate_report` | Client-side draft validation; the enforcement point |

## 3. Stages and limits (`src/climateadapt/agent/workflow.py`)

`run_agent(scenario, deps, provider, config)` runs each stage at most once, in
order. Outcomes: `complete` (draft accepted), `partial` (labelled fallback),
`failed` (no report could be grounded — never fabricated).

Hard limits (`AgentConfig`, all recorded on the trace):

| Limit | Default | Breach behavior |
|---|---|---|
| `max_steps` | 32 | Abort to finalize |
| `max_tool_calls` | 16 | Abort to finalize (the draft stage never runs) |
| `max_llm_calls` | 1 | Draft refused |
| `max_repair_attempts` (P18) | 0 | 0 = no repair; 1 = one repair attempt inside validate |
| `token_budget` (prompt + completion) | 100000 | Over-budget draft discarded → fallback |
| `total_timeout_seconds` | 600 | Abort to finalize |
| `llm_timeout_seconds` (per-call) | 180 | Enforced by the provider (httpx timeout) |
| Loop detection | always on | Any revisited stage aborts with `loop-detected` |

`temperature` (default `None`, i.e. unset) is passed through to the request and
logged; `seed` is never set (verified unsupported by the model) and the trace
records `"seed": "unsupported-by-model; not set"`. Draft default
`max_tokens=16000` (P09's 4000 was consumed entirely by reasoning).

## 4. Failure policy

- Retrieval failure/emptiness is non-fatal: the run proceeds without evidence
  (recorded as a warning; drafts then cite tool outputs only).
- Bundle failure, ranking failure, provider error, unparsable draft, invalid
  draft, or any limit breach → the labelled deterministic fallback built from
  whatever deterministic outputs exist (ranking may still run once in
  finalize: bounded, offline, no LLM). Missing values stay missing.
- Bad inputs, missing deps, no bundle, or no ranking → `failed`, report `None`.

## 5. Trace (`src/climateadapt/agent/trace.py`)

Every run returns a `RunTrace`: run id, versions, scenario, config, per-stage
records (status, timing, error codes), per-tool records (ok, timing, input /
output summaries), validator verdicts, token usage, outcome, problems,
warnings. Secrets can never appear (the scenario carries no credentials);
retrieved passage text is excluded (chunk ids + scores only) so a trace is not
a corpus redistribution channel; long summaries are cut with a marker. Traces
are returned in-memory; scripts persist them under git-ignored `data/`.

## 6. Live end-to-end run — RAN 2026-10-31 (1 call, owner-tasked)

`scripts/run_agent.py` on the reference scenario (warm caches, BM25 top-5):

```text
status: partial (all 7 stages ok; draft produced but rejected by validator)
tool_calls: 4; llm_calls: 1; total: 97.4 s
tokens: prompt=26965 completion=15087 (≈$0.098 at list rates)
problems: 44 (unknown-tool-output x22, undeclared-number x12,
  citation-mismatch x2, missing-ranking-ref x2, efficacy-claim x2,
  missing-provenance x2, missing-constraints-ref x1, draft-rejected x1)
saved: data\agent_runs\run-20261031T151438Z.json + -trace.json (git-ignored)
```

What happened: with `max_tokens=16000` the model produced a full draft, but it
**invented its own tool-output id scheme** (`environmental_bundle`,
`environmental_bundle:entries[0].result.spi`) instead of the registry ids
(`bundle`, `chirps_spi` + field), left numbers undeclared, altered two
citations, omitted ranking/constraints refs, and stated two efficacy claims.
The P09 validator caught all 44 problems and the labelled fallback was served.
The saved fallback re-validates clean offline, and retrieval reproduced
bit-identical chunk ids on re-run.

Finding (see KI-35): the prompt shows TOOL DATA as raw bundle/ranking JSON but
never states the registry's `(output_id, field)` vocabulary, so the model
guessed a JSONPath-like scheme. Worse, the TOOL DATA block labels were
literally `environmental_bundle` and `recommendations` — the exact fake ids
the draft used. P18 fix (implemented + fake-provider-tested 2026-11-01, live
acceptance still UNVERIFIED): an ALLOWED IDS AND VALUES block with the exact
registry vocabulary plus a worked `numbers[]` example, renamed block labels
(`bundle-json`, `ranking-json`), full per-chunk citation fields for verbatim
copying, and at most one repair attempt (`max_repair_attempts`, default 0;
`scripts/run_agent.py` enables it with `--repair 1 --max-llm-calls 2`).
No model draft has been accepted yet; do not present draft acceptance as
demonstrated.
