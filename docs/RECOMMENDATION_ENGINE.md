# Recommendation Engine (P08)

Deterministic, evidence-linked ranking of adaptation interventions. No LLM is
involved: Pydantic schemas plus pure functions map a scenario and an
environmental bundle to ranked options, exclusions with machine-readable
reasons, explicit unknowns, and manifest-grounded evidence references.

## Components

| File | Purpose |
|---|---|
| `src/climateadapt/recommend/schema.py` | Catalog, scenario, and response schemas (`extra="forbid"`) |
| `src/climateadapt/recommend/catalog.json` | Versioned catalog data (currently v1, 3 entries) |
| `src/climateadapt/recommend/loader.py` | Offline catalog loading (packaged file or explicit path) |
| `src/climateadapt/recommend/evidence.py` | Evidence-strength rubric + citation formatting |
| `src/climateadapt/recommend/constraints.py` | Deterministic hard constraints |
| `src/climateadapt/recommend/ranking.py` | Transparent scoring, deterministic ties |
| `src/climateadapt/recommend/service.py` | `recommend()` entry point + fixed limitations |
| `src/climateadapt/recommend/validate.py` | Offline catalog validation logic |
| `scripts/validate_catalog.py` | CLI wrapper (manifest + ingested-corpus checks) |

## Catalog entries

Each entry carries: id, name, category, description, applicability (crop
types, water requirement, production systems, soil, climate regime, farm
scale — every attribute may be `null` = unknown), benefit/cost/risk (the
literal `"unknown"` unless a cited source states them, with evidence-index
lists), evidence links (manifest `doc_id` + PDF page + short locator, no
quotes), evidence status (`supported` | `needs_evidence`), and the bundle
indicators relevant to it.

Current catalog (v1, deliberately small — the ingested corpus mainly supports
irrigation; see KI-26):

| id | status | evidence |
|---|---|---|
| `deficit-irrigation` | supported | IDDP66 PDF pp. 22, 70 (Ky factors; programme design example) |
| `irrigation-scheduling` | supported | IDDP66 PDF pp. 25, 66 (CROPWAT; seasonal scheduling) |
| `supplemental-irrigation` | needs_evidence, excluded | ICARDA docs in manifest but not ingested; no page links written |

Evidence pages were picked by searching the locally ingested IDDP66 chunks
for the corresponding sections (Ky/deficit-irrigation discussion, CROPWAT
scheduling, AquaCrop scheduling); the validator confirms each page exists and
holds extractable text. Benefit, cost and risk are `unknown` for every entry:
no efficacy, cost or yield figure is claimed anywhere.

## Evidence-strength rubric

Defined in `evidence.py`, count-based and deterministic:

| level | name | meaning |
|---|---|---|
| 0 | needs_evidence | marked `needs_evidence`, or no resolvable link → excluded from ranking |
| 1 | single_source | ≥1 resolvable link, all in one document |
| 2 | multi_source | resolvable links spanning ≥2 documents |

A link is resolvable when its document is ingested (or, when no ingested set
is supplied, when the entry is marked `supported`). Normalized score =
level / 2, i.e. {0.0, 0.5, 1.0}. The rubric counts traceable links only; it
says nothing about study quality or effect sizes.

## Hard constraints

Defined in `constraints.py`, evaluated in fixed order, all applicable reasons
reported. Unknowns never exclude — they are recorded in `unknowns`.

| code | rule |
|---|---|
| `needs_evidence` | entry lacks ingested corpus evidence |
| `no_water_source` | entry requires water, scenario has none |
| `no_irrigation_equipment` | irrigation entry, scenario has no equipment |
| `production_system_mismatch` | scenario system outside the entry's scope |
| `crop_not_applicable` | scenario crop outside the entry's crop list (case-insensitive) |

Unknown codes (`water_source_unknown`, `catalog_crop_scope_unknown`,
`benefit_unknown`, …) are listed per ranked option in a fixed order.

## Ranking

`total = 0.5 * evidence_strength + 0.3 * indicator_relevance + 0.2 * constraint_fit`
(weights are module constants in `ranking.py`, echoed in every response —
there are no hidden weights).

* `evidence_strength`: rubric level / 2.
* `indicator_relevance`: fraction of the entry's relevant bundle indicators
  with status `ok`. Availability only — indicator *values* are never
  interpreted, so no severity reading enters through the score.
* `constraint_fit`: 1.0 for every ranked option by construction (excluded
  options are not ranked). Kept explicit so the breakdown shows the gate.

Every ranked option exposes `score_components`, `score_weights`,
`score_inputs` (evidence level, evidence doc ids, per-indicator statuses,
exclusion count), `unknowns`, formatted evidence references, and the raw
benefit/cost/risk strings. Ties break by `intervention_id` ascending.

## Validation

`uv run python scripts/validate_catalog.py` checks: schema validity, unique
ids, every evidence `doc_id` in the manifest, every page within the ingested
range with extractable text, `supported` entries link only to ingested docs,
`needs_evidence` entries link nowhere, expected sources in the manifest, and
flags quantitative expressions in free text plus cited docs with unverified
manifest fields. Exit 0 on no errors (warnings allowed); `--require-ingested`
fails when the processed corpus is absent instead of skipping those checks.

## Limits (also returned verbatim in every response)

* Ranking reflects evidence traceability and indicator availability, not
  measured effectiveness.
* Benefit, cost and risk are unknown unless a cited source states them.
* Indicator values are not interpreted as drought severity.
* Catalog v1 covers irrigation options only; other adaptation options are not
  ranked.
* The validator checks traceability (doc + page exist), not semantic support:
  whether a page truly backs an entry stays an owner-review item.
* Ranker raises `KeyError` when evidence misses the manifest: only validated
  catalogs may be recommended from.
