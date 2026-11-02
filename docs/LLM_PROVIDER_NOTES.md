# LLM Provider Notes — Baseten Model APIs + Muse Spark Open (P03)

Access date for all documentation below: 2026-10-30. Method: read current official
Baseten documentation pages (exact URLs cited per fact). Nothing here is guessed; items
not found in the docs are marked UNVERIFIED. No live Baseten calls were made while
writing the docs section; see §3 for the smoke-test outcome.

## 1. Verified facts (with evidence)

### Base URL — VERIFIED

- Model APIs (hosted models, no deployment needed) use the shared OpenAI-compatible
  base URL **`https://inference.baseten.co/v1`**.
- Sources: [Inference overview](https://docs.baseten.co/inference/overview) ("Model APIs
  use the shared base URL `https://inference.baseten.co/v1`"), [Chat Completions
  reference](https://docs.baseten.co/reference/inference-api/chat-completions.md) (Python,
  JS, and cURL examples all use it), [Muse Spark Open library
  page](https://www.baseten.co/library/muse-spark-open/) (sample code uses it).
- This confirms the base URL already noted in `.env.example` (commit `cf037d3`).

### Authentication — VERIFIED

- Header: **`Authorization: Bearer $BASETEN_API_KEY`** with a Baseten API key created in
  the Baseten account; every official example reads the key from the **`BASETEN_API_KEY`**
  environment variable.
- Sources: [Chat Completions
  reference](https://docs.baseten.co/reference/inference-api/chat-completions.md) (cURL:
  `-H "Authorization: Bearer $BASETEN_API_KEY"`; OpenAPI `security: BearerAuth`),
  [API keys](https://docs.baseten.co/organization/api-keys.md) (key management).
- App mapping: the app accepts `CLIMATEADAPT_BASETEN_API_KEY` (repo convention) and
  `BASETEN_API_KEY` (Baseten docs convention, already in `.env.example`); see `config.py`.

### Request/response shape — VERIFIED

- Route: **`POST {base_url}/chat/completions`** with the OpenAI Chat Completions format
  (`model`, `messages`, plus standard parameters). A success returns OpenAI-shaped
  `chat.completion` with `choices[].message`, `finish_reason`, and `usage`
  (`prompt_tokens`, `completion_tokens`, `total_tokens`,
  `prompt_tokens_details.cached_tokens`).
- Sources: [Chat Completions
  reference](https://docs.baseten.co/reference/inference-api/chat-completions.md)
  ("fully compatible with the OpenAI Chat Completions API"), [Pricing and
  limits](https://docs.baseten.co/inference/model-apis/pricing-and-limits) (annotated
  response example), OpenAPI spec at
  `https://docs.baseten.co/reference/inference-api/llm-openapi-spec.json`.
- Alternative protocols exist (OpenAI Responses, Anthropic Messages beta) but are OUT OF
  SCOPE for this spike; the app targets Chat Completions only.

### Model identifier string — PARTIALLY VERIFIED

- The official [Muse Spark Open library
  page](https://www.baseten.co/library/muse-spark-open/) and the "Try model API" link
  (`app.baseten.co/model-apis/meta-models/muse-spark-open`) use slug
  **`meta-models/muse-spark-open`**.
- The owner-stated slug **`meta-models/muse-spark-open-1026`** (app default) was NOT found
  in official Baseten documentation; it appears only in a third-party hackathon repo
  using Baseten. **It was verified live on 2026-10-30: all smoke calls with this slug
  returned HTTP 200 (see §3).** If it ever 404s, fall back to the documented
  `meta-models/muse-spark-open`. The model id stays a setting, not a constant. Do NOT
  assume any other model ID or provider exists (AGENTS.md §8).

### Tool / function calling — VERIFIED (docs)

- Supported: "The language models in this table support [tool
  calling](https://docs.baseten.co/inference/function-calling.md)" ([Model APIs
  overview](https://docs.baseten.co/inference/model-apis/overview.md#feature-support)),
  and the [library page](https://www.baseten.co/library/muse-spark-open/) describes
  "reliable tool use".
- Wire format is OpenAI-compatible: `tools: [{type: "function", function: {name,
  description, parameters (JSON Schema), strict}}]`, `tool_choice` (`"required"` forces
  a call), results returned as `role: "tool"` messages with `tool_call_id`, terminal
  `finish_reason` of `"stop"` or `"tool_calls"`, and a `refusal` field to check.
- Source: [Function calling](https://docs.baseten.co/inference/function-calling.md).
- Live behavior verified 2026-10-30 (see §3): one tool-call round trip succeeded — the model returned the correct function and arguments, and the follow-up with the tool result was answered correctly.

### Structured output / JSON mode — VERIFIED UNSUPPORTED for this model (docs)

- "Model APIs support structured outputs **except for Muse Spark Open, which accepts
  `json_schema` but doesn't enforce the schema**" ([Structured
  outputs](https://docs.baseten.co/inference/structured-outputs.md)). Likewise, "All
  except Muse Spark Open support structured outputs and JSON mode" ([Model APIs
  overview](https://docs.baseten.co/inference/model-apis/overview.md#feature-support)).
- Consequence for P09/P10: **do not rely on server-side schema enforcement.** The P09
  validator must parse and validate the report client-side (Pydantic) and treat any
  non-conforming output as a validation failure with deterministic fallback. Prompt the
  model to emit JSON, then verify — never trust. The model *happened* to emit valid
  JSON on the single live attempt (see §3) — one anecdote, not a guarantee; schema
  compliance is still unenforced server-side and must be validated client-side every time.

### Streaming — VERIFIED (docs, page level)

- "Streaming returns output incrementally. OpenAI- and Anthropic-compatible APIs use
  server-sent events" ([Inference
  overview](https://docs.baseten.co/inference/overview)); details on the [Streaming
  page](https://docs.baseten.co/inference/streaming.md) (not read in depth — out of scope
  for the smoke test). Live streaming behavior UNVERIFIED.

### Pricing / credits — VERIFIED (docs)

- [Muse Spark Open library page](https://www.baseten.co/library/muse-spark-open/): **$1.25
  / 1M input tokens, $0.15 / 1M cached input tokens, $4.25 / 1M output tokens.** Model APIs
  bill per token; rates vary by model ([Pricing and
  limits](https://docs.baseten.co/inference/model-apis/pricing-and-limits)). Workspace
  budgets, per-key/user/model cost attribution, and usage inspection are supported
  (same page).
- The owner's actual credit balance and budget are UNVERIFIED — must be obtained from the
  owner before any live calls beyond the tiny smoke test.

### Rate limits — VERIFIED (docs, mechanics only)

- Per-model requests-per-minute plus token metering (some models split input/output);
  `429 Too Many Requests` on exhaustion; limits replenish continuously; retry with
  exponential backoff; `529` means Baseten shed load ([Pricing and
  limits](https://docs.baseten.co/inference/model-apis/pricing-and-limits)).
- Numeric RPM/TPM limits for Muse Spark Open are UNVERIFIED (per-model table values were
  not retrievable as text). Session-affinity guidance (≤ ~60 RPM per session) is
  documented on the same page.

### Error codes — VERIFIED (docs)

- [Inference errors](https://docs.baseten.co/inference/errors): `400/401/403/404` =
  malformed request / bad key / wrong model slug / wrong endpoint; `402` = billing;
  `413` = body too large; `429` = rate limit or no capacity; `499` = client disconnect;
  `500/502/503/504` = internal/gateway/transient; `529` = shed load. Error-body shape
  varies (`{"error": "<message>"}` or structured object) — inspect message/code, never
  infer from shape alone. On persistent failures, save model slug, timestamp, status,
  error body, and the `x-baseten-request-id` header.

### Muse Spark Open quirks — VERIFIED (docs)

- Accepts `logprobs`/`top_logprobs` but ignores them (returns none); `n > 1` returns
  HTTP 400; neither `seed` nor `temperature: 0` guarantees reproducibility; audio input
  supported ([Model APIs
  overview](https://docs.baseten.co/inference/model-apis/overview.md#defaults-and-limitations)).
  The app must therefore never request `n > 1` or depend on seed reproducibility.

## 2. UNVERIFIED items (not found in docs or needs a live call)

- Numeric RPM/TPM rate limits and max context/output tokens for this model (per-model
  table not retrievable as text; third-party pages REPORT a 1M-token context — REPORTED
  only, not verified).
- Live behavior beyond the §3 smoke run: streaming, larger generations, error shapes
  other than the malformed-body 400, retry/backoff behavior, credit balance/budget.
- `x-session-affinity` usefulness, Anthropic/Responses protocols, web search tools.
- (Resolved by §3: the `-1026` slug, basic completion shape, tool-call round trip,
  unenforced-`json_schema` behavior on one attempt, malformed-body error shape,
  latency ballpark, `usage` accounting.)

## 3. Live smoke — RAN 2026-10-30 (5 calls, owner-approved)

Command (flag set for that one process only; key present via environment, never printed):

```powershell
$env:CLIMATEADAPT_RUN_LIVE_LLM = "1"; uv run python scripts/llm_smoke.py
```

Result: exit 0, 5/5 calls made, total usage prompt=1206 / completion=191 tokens
(≈$0.002 at list rates). Verbatim outcome lines:

```text
base_url: https://inference.baseten.co/v1
model: meta-models/muse-spark-open-1026
[a/trivial] HTTP 200 in 6125 ms
[a/trivial] finish_reason=length
[a/trivial] content: None
[b/json-schema] HTTP 200 in 797 ms
[b/json-schema] client-side parse valid=True
[b/json-schema] content: {"answer": "pong"}
[c/tool-call] HTTP 200 in 781 ms
[c/tool-call] finish_reason=length
[c/tool-call] tool_calls=1
[c/tool-call] add({"a": 3.14, "b": 3.14})
[c/tool-result] HTTP 200 in 719 ms
[c/tool-result] content: 3.14 + 3.14 = 6.28
[d/malformed] HTTP 400 in 188 ms
[d/malformed] error body: {"error": "Invalid request body"}
```

Verified live:

- The `-1026` slug works (HTTP 200 on all well-formed calls).
- Tool calling works end to end: correct function and arguments
  (`add({"a": 3.14, "b": 3.14})`), follow-up with the tool result answered correctly.
- `response_format: json_schema` is accepted and the model complied on this attempt
  (client-side parse valid) — but per §1 it is NOT enforced server-side, so P09 must
  still validate client-side and fall back on any mismatch.
- Malformed request (`{}`) → HTTP 400 with body `{"error": "Invalid request body"}`.
- `usage` accounting is returned, including `prompt_tokens_details.cached_tokens`
  (128 cached tokens observed on each call) and `completion_tokens_details` with
  `reasoning_tokens`.

Warnings for P09/P10 (observed):

- This is a reasoning model: `reasoning_tokens` consume `max_tokens`. With tiny budgets
  the visible content can be cut (`finish_reason=length`, content `None` in probe (a)).
  P09 must set generous completion budgets and treat `length` as "budget too small",
  not as a model failure.
- First call took 6.1 s (cold), later calls ~0.7–0.8 s. P09/P10 timeouts must allow
  multi-second latency plus queueing.
- Probe (e), a rate-limit probe, was deliberately skipped: hammering limits is unsafe.
  No rate-limit or credit-balance information was returned or requested.

## 4. P09 adapter + live report call — RAN 2026-10-31 (1 call, owner-tasked)

Adapter: `src/climateadapt/llm/` (`provider.py` protocol + Baseten + fake,
`report.py` schema + tool-output registry, `validator.py` client-side checks,
`fallback.py` deterministic fallback, `prompts/` templates, `service.py`
draft-or-fallback orchestration). The provider implements only this document's
verified API: `POST {base}/chat/completions`, Bearer auth, no `n > 1`, bounded
retries with backoff on 429/529/5xx + transport errors (honouring Retry-After),
typed errors, secret-safe logging, usage accounting incl. cached tokens.

Live call (`scripts/llm_report.py`, gate + key set for that one process only):
warm-cache 4/4-ok bundle + offline BM25 top-5 + deterministic ranking, then one
`meta-models/muse-spark-open-1026` completion (`max_tokens=4000`):

```text
bundle statuses: 4/4 ok (warm cache, downloads forced off)
retrieved: 5 chunks (IDDP66 x4, WR45 x1); ranking: 2 ranked, 1 excluded
accepted: False (fallback=True)
latency_ms: 46641; attempts: 1
usage: prompt_tokens=26965 completion_tokens=4000 total=30965 cached=0
problems: [empty-content] Model returned no text (finish_reason=length).
saved: data\llm_reports\report-20261031T143521Z.json (git-ignored)
```

Verified live: the adapter path works end to end (HTTP 200, usage returned);
the validator correctly rejected the empty draft and the labelled fallback was
served (4 findings, 5 citations, 2 ranked + 1 excluded, 4 limitations); the
saved fallback re-validates clean offline (`allow_fallback=True`, 0 problems).
Cost ≈ $0.051 at list rates (26965 in × $1.25 + 4000 out × $4.25 per 1M).

Lesson (confirms the §3 warning, now with a real prompt): `max_tokens=4000`
is far too small for this reasoning model on a ~27k-token prompt — all 4000
completion tokens went to reasoning and the visible content was cut. A retry
that accepts a model draft needs a much larger completion budget (and the
prompt trimmed: the full bundle + ranking JSON is verbose). NOT retried: the
task authorised one call. No second call was made; credit balance still
UNVERIFIED.

## 5. P18 prompt registry + repair attempt — NOT RUN LIVE (2026-11-01)

P18 changed the prompt, not the validator (KI-35): the draft request now
carries an ALLOWED IDS AND VALUES block (`format_registry_block`: every
registry `(output_id, field)` value, ranking/constraints texts and reason
codes, allowed evidence ids, repeatable dates, banned invented schemes, one
worked `numbers[]` example built from the run's real values), full citation
fields per retrieved chunk (verbatim `citation`/`pages`/`landing_url`/
`license`/`license_status`), renamed TOOL DATA block labels (`bundle-json`,
`ranking-json` — the old labels `environmental_bundle`/`recommendations` were
the exact strings the P10 draft copied as fake ids), and stronger verbatim
instructions. The agent also supports at most one repair attempt
(`AgentConfig.max_repair_attempts`, 0/1, default 0): the validator's problems
plus a capped draft excerpt go back to the model once, and the repair output
is validated exactly as before; any failure still ships the labelled
deterministic fallback. Validator rules are unchanged — every historic
failure class is still rejected (fake-provider tests).

`max_tokens` decision (checked against this document): the P10 run finished
`finish_reason=stop` with 15087/16000 completion tokens, so 16000 suffices
for a full draft and is kept. No numeric max-output limit for this model was
found in the cited Baseten docs (§2, still UNVERIFIED), so raising the budget
further has no verified basis and was NOT done. Model ID and endpoint are
unchanged (`meta-models/muse-spark-open-1026`,
`https://inference.baseten.co/v1/chat/completions`).

No live call was made in P18: the `CLIMATEADAPT_RUN_LIVE_LLM=1` gate was off
in the agent session, so the budget (max 3 calls, ~$0.50) was unspent ($0.00)
and draft acceptance is still UNVERIFIED. Owner retry (reference scenario,
draft + one repair = at most 2 calls):

```powershell
$env:CLIMATEADAPT_RUN_LIVE_LLM = "1"
.venv/Scripts/python.exe scripts/run_agent.py
```

## 6. 2026-11-02 live agent run + P22 validator/prompt fix — RAN (owner), fix UNVERIFIED live

Owner ran the P18 prompt + one repair live (reference scenario):

```powershell
$env:CLIMATEADAPT_RUN_LIVE_LLM = "1"
.venv/Scripts/python.exe scripts/run_agent.py
```

```text
status: partial (all 7 stages ok; draft produced, repair also rejected)
tool_calls: 5; llm_calls: 2; total: 91.1 s
tokens: prompt=61698 completion=24625
problems: 7 (undeclared-number x5, efficacy-claim x1, draft-rejected x1)
saved: data\agent_runs\run-20261102T141454Z.json + -trace.json (git-ignored)
```

Problems fell 44 → 7. All five `undeclared-number` hits are the numeral `'5'`
in `data_coverage`, `environmental_findings[1..3]`, `limitations[2]`; the
`efficacy-claim` is the repair's `ranked_recommendations[0]` (the first draft
had no efficacy problem — the repair introduced one). Cost: confirm from the
Baseten dashboard, not from an estimate (list rates §1: $1.25/$4.25 per 1M
in/out tokens).

P22 diagnosis (offline, CONFIRMED): H1 CONFIRMED — the validator's numeral scan
(`NUMBER_RE`) matches the `5` inside `ERA5`/`ERA5-Land`, and `_strip_known`
only strips full `data_source` echoes, so a bare dataset name always fails;
only the three ERA5 findings were flagged (CHIRPS finding never), and the
exact problem string was reproduced on a synthetic draft. H2 CONFIRMED as
mechanism — `efficacy-claim` fires only on an `EFFICACY_RE` match in a ranked
narrative — but the exact phrase is unrecoverable: neither the draft nor the
repair output was saved in the trace.

P22 changes (all offline-tested, live acceptance still UNVERIFIED): **yes, the
validator was changed — one narrow bug fix.** Digits inside known
dataset/product identifiers (`ERA5`, `ERA5-Land`, `CHIRPS v3`/`v3.0`, one
`DATASET_IDENTIFIER_RE` constant) no longer count as numeric claims; every
other rule is untouched (bare `3`/`5`, resolutions, years outside a full echo,
invented ids, altered citations, and real effect claims are still rejected —
pinned by tests). The system prompt now restricts ranked narratives to
restating the platform score, catalog echoes, and cited evidence (effect verbs
banned, one compliant example), the two problem strings carry the offending
sentence + matched phrase into the repair turn, and the trace keeps
`draft_text`/`repair_text` verbatim for debugging. Owner retry budget: at most
2 runs × 2 calls with the gate set (same command as above); if still rejected
after the second run, stop and report.

## 7. 2026-11-02 live run of the P22 build + P23 acceptance change — RAN (owner)

Owner ran the P22 prompt/validator live (reference scenario, same command as
§6):

```text
status: partial (all 7 stages ok; first draft unparsable, repair rejected)
tool_calls: 5; llm_calls: 2; total: 91.0 s
tokens: prompt=60629 completion=24391
problems: 5 (first draft 1, repair 4, plus draft-rejected)
saved: data\agent_runs\run-20261102T155950Z.json + -trace.json (git-ignored)
```

The P22 fixes held: no ERA5 `'5'` flag, no efficacy-claim. The first draft hit
`finish=length` (16000/16000 completion tokens, cut mid-string → 1
`invalid-json` problem). The repair was valid JSON with 4 `undeclared-number`
problems: `'0'`/`'7'` ("soil moisture layer 0-7 cm"), `'7.8'` (land-fallback
km), `'0.05'` (CHIRPS resolution). None is declarable — layer ranges,
resolutions, and the nested `land_fallback.distance_km` (tool value
7.842441576259394; the model wrote the warning's rounded 7.8) are not registry
values — so all four rejections are correct. Cost: confirm from the Baseten
dashboard, not from an estimate.

P23 changes what happens next (no new live call yet — all offline-tested).
**The validator is unchanged except the sentence-splitter fix** (evidence
quotes no longer split on decimal points or `e.g.`; which numerals flag is
untouched). The prompt now states the strict policy — a numeral only if it
appears in the registry with exactly that value, everything else words — and
the repair turn is told to "replace the number with words or delete the
sentence; do not add new numbers". Acceptance is statement-level
(owner-approved, see `AGENT_WORKFLOW.md` §8): valid model statements ship,
failing ones are replaced by the fallback counterpart, the composite is
re-validated as a whole, and anything else falls back. Owner budget: at most
2 runs; if still `fallback` after two, stop and report.

## 8. Using your own key (judges and reviewers)

Base URL, model ID, and key are all plain environment configuration — no code
change is needed to point the app at your own Baseten account. Never commit a
real key; the app key and any coding-agent auth are separate things.

| Setting | Env var (preferred) | Alt | Default |
|---|---|---|---|
| API base URL | `CLIMATEADAPT_BASETEN_BASE_URL` | — | `https://inference.baseten.co/v1` |
| Model ID | `CLIMATEADAPT_BASETEN_MODEL_ID` | — | `meta-models/muse-spark-open-1026` |
| API key | `CLIMATEADAPT_BASETEN_API_KEY` | `BASETEN_API_KEY` | none (required for live calls) |
| Live-call gate | `CLIMATEADAPT_RUN_LIVE_LLM=1` | — | unset (live scripts refuse to run) |

No other provider's endpoint is documented or supported here: the adapter
implements only the verified Baseten Chat Completions call above (AGENTS.md
§8). Without a key the app serves deterministic outputs plus the labelled
fallback (`[provider-auth]`), which is the expected offline behavior.
