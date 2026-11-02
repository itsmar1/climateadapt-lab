/** Synthetic fixtures mirroring the backend shapes (never real user data). */

import { vi } from 'vitest';
import type { Mock } from 'vitest';
import type { components } from '../api/schema';

export type BundleEntry = components['schemas']['BundleIndicatorResult'];
export type ScenarioDetailFixture = components['schemas']['ScenarioDetail'];

type Report = NonNullable<ScenarioDetailFixture['report']>;

function statement(text: string): Report['summary'] {
  return { text, evidence_ids: [], tool_output_ids: ['bundle'], numbers: [] };
}

export function reportFixture(fallback: boolean): Report {
  return {
    schema_version: 1,
    generator: fallback ? 'deterministic-fallback' : 'fake:test-model',
    fallback,
    fallback_note: fallback ? 'Model output rejected (test); deterministic values only.' : null,
    summary: statement('Synthetic summary.'),
    environmental_findings: [statement('Synthetic finding.')],
    evidence: [],
    ranked_recommendations: [],
    excluded_options: [],
    limitations: ['Synthetic limitation.'],
    assumptions: [],
    data_coverage: statement('Synthetic coverage.'),
    provenance_refs: ['bundle'],
  };
}

export function traceFixture(): NonNullable<ScenarioDetailFixture['trace']> {
  return {
    run_id: 'run-test',
    agent_version: 1,
    started_at: '2026-10-31T00:00:00+00:00',
    ended_at: '2026-10-31T00:00:01+00:00',
    duration_ms_total: 1000,
    draft_text: '',
    repair_text: '',
    scenario: {},
    config: {},
    component_versions: {},
    stages: [],
    tool_calls: [],
    validator_verdicts: [],
    usage: null,
    outcome: 'complete',
    problems: [],
    warnings: [],
  };
}

export function rankingFixture(): NonNullable<ScenarioDetailFixture['ranking']> {
  return {
    catalog_version: 1,
    scenario: {},
    ranked: [],
    excluded: [],
    warnings: [],
    limitations: ['Synthetic ranking limitation.'],
  };
}

export function bundleFixture(
  entries: BundleEntry[],
): NonNullable<ScenarioDetailFixture['bundle']> {
  return {
    indicator: 'environmental_bundle',
    latitude: 30.43,
    longitude: -9.61,
    target_end_month: '2024-03',
    timescale_months: 3,
    reference_start_year: 1991,
    reference_end_year: 2020,
    entries,
  };
}

export function spiEntryOk(): BundleEntry {
  return {
    indicator: 'chirps_spi',
    status: 'ok',
    error_type: null,
    error_message: null,
    requested_latitude: 30.43,
    requested_longitude: -9.61,
    grid_point_latitude: 30.425,
    grid_point_longitude: -9.625,
    result: {
      data_source: 'CHIRPS v3.0',
      timescale_months: 3,
      target_window_start: '2024-01',
      target_window_end: '2024-03',
      window_total_mm: 76.87,
      spi: -0.517,
      cumulative_probability: 0.303,
      reference_years_used: 30,
      reference_years_included: [1991, 1992],
      reference_years_excluded: [{ year: 1993, reason: 'incomplete' }],
      reference_spi_mean: 0.012,
      reference_spi_std: 1.004,
      reference_start_year: 1991,
      reference_end_year: 2020,
      point_on_cell_boundary: true,
      target_in_reference_period: false,
      citation: 'Funk et al. (2015).',
      doi: '10.1038/sdata.2015.66',
      license_note: 'Free for research.',
      limitations: ['Precipitation only; not a drought verdict.'],
    },
  };
}

export function tempEntryOkWithFallback(): BundleEntry {
  return {
    indicator: 'era5_temperature_anomaly',
    status: 'ok',
    error_type: null,
    error_message: null,
    requested_latitude: 30.43,
    requested_longitude: -9.61,
    grid_point_latitude: 30.4,
    grid_point_longitude: -9.6,
    result: {
      data_source: 'ERA5-Land',
      timescale_months: 3,
      target_window_start: '2024-01',
      target_window_end: '2024-03',
      window_mean_c: 18.5,
      reference_mean_c: 16.282,
      anomaly_c: 2.218,
      reference_sd_c: 0.9,
      standardized_anomaly: 2.464,
      percentile_rank: 0.967,
      reference_years_used: 30,
      reference_years_included: [1991, 1992],
      reference_years_excluded: [],
      reference_start_year: 1991,
      reference_end_year: 2020,
      land_fallback: {
        max_distance_km: 15,
        used: true,
        reason: 'masked',
        nearest_grid_point_latitude: 30.4,
        nearest_grid_point_longitude: -9.6,
        selected_grid_point_latitude: 30.5,
        selected_grid_point_longitude: -9.6,
      },
      citation: 'Muñoz-Sabater et al. (2021).',
      doi: '10.5194/essd-13-4349-2021',
      license_note: 'Copernicus licence.',
      limitations: ['Reanalysis, not station data.'],
    },
  };
}

export function soilEntryOk(): BundleEntry {
  return {
    indicator: 'era5_soil_moisture_anomaly',
    status: 'ok',
    error_type: null,
    error_message: null,
    requested_latitude: 30.43,
    requested_longitude: -9.61,
    grid_point_latitude: 30.4,
    grid_point_longitude: -9.6,
    result: {
      data_source: 'ERA5-Land',
      variable: 'volumetric_soil_water_layer_1',
      layer_depth: '0–7 cm',
      timescale_months: 3,
      target_window_start: '2024-01',
      target_window_end: '2024-03',
      window_mean_m3m3: 0.2,
      reference_mean_m3m3: 0.2505,
      anomaly_m3m3: -0.0505,
      reference_sd_m3m3: 0.02,
      percentile_rank: 0.1,
      reference_years_used: 30,
      reference_years_included: [1991],
      reference_years_excluded: [],
      reference_start_year: 1991,
      reference_end_year: 2020,
      land_fallback: null,
      citation: 'Muñoz-Sabater et al. (2021).',
      doi: '10.5194/essd-13-4349-2021',
      license_note: 'Copernicus licence.',
      limitations: ['Topsoil layer only.'],
    },
  };
}

export function failedEntry(): BundleEntry {
  return {
    indicator: 'era5_spi',
    status: 'failed',
    error_type: 'data_not_available',
    error_message: 'No data for the requested window.',
    requested_latitude: 30.43,
    requested_longitude: -9.61,
    grid_point_latitude: null,
    grid_point_longitude: null,
    result: null,
  };
}

export function skippedEntry(): BundleEntry {
  return {
    indicator: 'era5_spi',
    status: 'skipped',
    error_type: null,
    error_message: null,
    requested_latitude: 30.43,
    requested_longitude: -9.61,
    grid_point_latitude: null,
    grid_point_longitude: null,
    result: null,
  };
}

export function undefinedEntry(): BundleEntry {
  return {
    ...spiEntryOk(),
    status: 'undefined',
    result: {
      ...(spiEntryOk().result as Record<string, unknown>),
      spi: null,
      message: 'Zero reference variance; SPI undefined.',
    },
  };
}

export function scenarioDetailFixture(
  overrides: Partial<ScenarioDetailFixture> = {},
): ScenarioDetailFixture {
  return {
    version: 1,
    scenario_id: 'sc-test',
    job_id: 'job-test',
    status: 'complete',
    created_at: '2026-10-31T00:00:00+00:00',
    updated_at: '2026-10-31T00:00:01+00:00',
    scenario: {
      latitude: 30.43,
      longitude: -9.61,
      target_end_month: '2024-03',
      timescale_months: 3,
      reference_start_year: 1991,
      reference_end_year: 2020,
      min_reference_years: 30,
      land_fallback_max_km: 15,
      indicators: ['chirps_spi'],
      query: 'deficit irrigation scheduling',
      top_k: 5,
      exclude_reference: true,
      crop: 'wheat',
      has_water_source: true,
      has_irrigation_equipment: true,
      production_system: 'irrigated',
      season: '2024-03',
    },
    bundle: bundleFixture([spiEntryOk()]),
    ranking: rankingFixture(),
    report: reportFixture(false),
    trace: traceFixture(),
    problems: [],
    warnings: [],
    ...overrides,
  };
}

export type ScriptedResponse = { body?: unknown; status?: number } | Error;

/**
 * Fetch mock that builds a FRESH Response per call (bodies are single-use).
 * The script repeats its last entry once exhausted.
 */
export function mockFetch(script: ScriptedResponse[]): Mock {
  let index = 0;
  return vi.fn().mockImplementation(() => {
    const next = script[Math.min(index, script.length - 1)] as ScriptedResponse;
    index += 1;
    if (next instanceof Error) {
      return Promise.reject(next);
    }
    if (next.status === 204) {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(
      new Response(JSON.stringify(next.body ?? null), {
        status: next.status ?? 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
}

export function scenarioCreatedFixture() {
  return {
    version: 1,
    scenario_id: 'sc-new',
    job_id: 'job-new',
    status: 'queued',
    status_url: '/v1/jobs/job-new',
    scenario_url: '/v1/scenarios/sc-new',
  };
}

export type ReportModel = NonNullable<ScenarioDetailFixture['report']>;
export type RankingModel = NonNullable<ScenarioDetailFixture['ranking']>;
export type StatementModel = ReportModel['summary'];
export type EvidenceItemModel = NonNullable<ReportModel['evidence']>[number];
export type RankedRecommendationModel = NonNullable<
  ReportModel['ranked_recommendations']
>[number];
export type ReportExcludedModel = NonNullable<ReportModel['excluded_options']>[number];
export type RankedOptionModel = RankingModel['ranked'][number];
export type RankingExcludedModel = RankingModel['excluded'][number];
export type EvidenceReferenceModel = RankedOptionModel['evidence'][number];

export function statementFixture(
  text: string,
  overrides: Partial<StatementModel> = {},
): StatementModel {
  return {
    text,
    evidence_ids: [],
    tool_output_ids: ['bundle'],
    numbers: [],
    ...overrides,
  };
}

export function evidenceItemFixture(
  overrides: Partial<EvidenceItemModel> = {},
): EvidenceItemModel {
  return {
    chunk_id: 'fao-iddp66-crop-yield-response-to-water:00001',
    doc_id: 'fao-iddp66-crop-yield-response-to-water',
    citation:
      'Steduto et al. (2012). Crop yield response to water. FAO. ' +
      'PDF p. 22 (printed p. 22).',
    pages: 'PDF p. 22 (printed p. 22)',
    landing_url: 'https://example.invalid/fao-iddp66',
    license: 'CC BY-NC-SA 3.0 IGO',
    license_status: 'verified_in_record',
    ...overrides,
  };
}

export function rankedRecommendationFixture(
  overrides: Partial<RankedRecommendationModel> = {},
): RankedRecommendationModel {
  return {
    intervention_id: 'deficit-irrigation',
    name: 'Deficit irrigation',
    benefit: 'unknown',
    cost: 'unknown',
    risk: 'unknown',
    narrative: statementFixture('Synthetic recommendation narrative.', {
      evidence_ids: ['fao-iddp66-crop-yield-response-to-water:00001'],
      tool_output_ids: ['ranking:deficit-irrigation'],
    }),
    ...overrides,
  };
}

export function reportExcludedFixture(
  overrides: Partial<ReportExcludedModel> = {},
): ReportExcludedModel {
  return {
    intervention_id: 'supplemental-irrigation',
    name: 'Supplemental irrigation of rainfed crops',
    reason_codes: ['needs_evidence'],
    narrative: statementFixture('Synthetic exclusion narrative.', {
      tool_output_ids: ['constraints:supplemental-irrigation'],
    }),
    ...overrides,
  };
}

export function evidenceReferenceFixture(
  overrides: Partial<EvidenceReferenceModel> = {},
): EvidenceReferenceModel {
  return {
    doc_id: 'fao-iddp66-crop-yield-response-to-water',
    pdf_page: 22,
    reference: 'yield response factors for wheat',
    citation:
      'Steduto et al. (2012). Crop yield response to water. FAO. ' +
      'PDF p. 22 (printed p. 22).',
    landing_url: 'https://example.invalid/fao-iddp66',
    license: 'CC BY-NC-SA 3.0 IGO',
    license_status: 'verified_in_record',
    unverified_fields: [],
    ...overrides,
  };
}

export function rankedOptionFixture(
  overrides: Partial<RankedOptionModel> = {},
): RankedOptionModel {
  return {
    intervention_id: 'deficit-irrigation',
    name: 'Deficit irrigation',
    category: 'irrigation',
    score_total: 1.0,
    score_components: {
      evidence_strength: 1.0,
      indicator_relevance: 1.0,
      constraint_fit: 1.0,
    },
    score_weights: {
      evidence_strength: 0.5,
      indicator_relevance: 0.3,
      constraint_fit: 0.2,
    },
    score_inputs: {
      evidence_level: 2,
      evidence_doc_ids: ['fao-iddp66-crop-yield-response-to-water'],
      indicator_statuses: { chirps_spi: 'ok' },
      exclusion_reasons: 0,
    },
    unknowns: ['soil type at the farm'],
    evidence: [evidenceReferenceFixture()],
    benefit: 'unknown',
    cost: 'unknown',
    risk: 'unknown',
    ...overrides,
  };
}

export function rankingExcludedFixture(
  overrides: Partial<RankingExcludedModel> = {},
): RankingExcludedModel {
  return {
    intervention_id: 'supplemental-irrigation',
    name: 'Supplemental irrigation of rainfed crops',
    category: 'irrigation',
    evidence_status: 'needs_evidence',
    reasons: [
      {
        code: 'needs_evidence',
        message: 'No resolvable evidence links; candidate manuals are not ingested.',
      },
    ],
    ...overrides,
  };
}

export function rankingFixtureFull(): RankingModel {
  return {
    catalog_version: 1,
    scenario: {},
    ranked: [rankedOptionFixture()],
    excluded: [rankingExcludedFixture()],
    warnings: ['Synthetic ranking warning.'],
    limitations: ['Synthetic ranking limitation.'],
  };
}

export function reportFixtureFull(fallback: boolean): ReportModel {
  return {
    schema_version: 1,
    generator: fallback ? 'deterministic-fallback' : 'fake:test-model',
    fallback,
    fallback_note: fallback ? 'Model output rejected (test); deterministic values only.' : null,
    summary: statementFixture('Synthetic summary.'),
    environmental_findings: [
      statementFixture('Synthetic finding with a traced value.', {
        evidence_ids: ['fao-iddp66-crop-yield-response-to-water:00001'],
        tool_output_ids: ['chirps_spi'],
        numbers: [
          {
            value: -0.517,
            unit: 'SPI',
            tool_output_id: 'chirps_spi',
            field: 'spi',
          },
        ],
      }),
    ],
    evidence: [evidenceItemFixture()],
    ranked_recommendations: [rankedRecommendationFixture()],
    excluded_options: [reportExcludedFixture()],
    limitations: ['Synthetic limitation.'],
    assumptions: ['Synthetic assumption.'],
    data_coverage: statementFixture('Synthetic coverage.'),
    provenance_refs: ['bundle', 'chirps_spi'],
  };
}

export function partialReportFixture(): ReportModel {
  const base = reportFixtureFull(false);
  return {
    ...base,
    generator: 'fake:test-model',
    acceptance: 'ai-partial',
    statement_origins: {
      summary: 'model',
      'environmental_findings[0]': 'model',
      'ranked_recommendations[0]': 'model',
      'excluded_options[0]': 'model',
      'limitations[0]': 'platform',
      'assumptions[0]': 'model',
      data_coverage: 'model',
    },
    replaced_statements: { 'limitations[0]': ['undeclared-number'] },
    dropped_statements: {},
  };
}

export function fullDetailFixture(
  overrides: Partial<ScenarioDetailFixture> = {},
): ScenarioDetailFixture {
  return scenarioDetailFixture({
    bundle: bundleFixture([spiEntryOk(), failedEntry()]),
    ranking: rankingFixtureFull(),
    report: reportFixtureFull(true),
    ...overrides,
  });
}

export type ScenarioSummaryModel = components['schemas']['ScenarioSummary'];
export type ScenarioListModel = components['schemas']['ScenarioList'];

export function scenarioSummaryFixture(
  overrides: Partial<ScenarioSummaryModel> = {},
): ScenarioSummaryModel {
  return {
    version: 1,
    scenario_id: 'sc-1',
    job_id: 'job-1',
    status: 'complete',
    created_at: '2026-10-31T00:00:00+00:00',
    updated_at: '2026-10-31T00:01:00+00:00',
    latitude: 30.43,
    longitude: -9.61,
    target_end_month: '2024-03',
    query: 'deficit irrigation scheduling',
    ...overrides,
  };
}

export function scenarioListFixture(
  items: ScenarioSummaryModel[],
  total: number,
  offset = 0,
): ScenarioListModel {
  return { version: 1, total, limit: 20, offset, items };
}

export type DemoSnapshotSummaryModel = components['schemas']['DemoSnapshotSummary'];
export type DemoSnapshotFileModel = components['schemas']['DemoSnapshotFile'];

export function demoSummaryFixture(
  overrides: Partial<DemoSnapshotSummaryModel> = {},
): DemoSnapshotSummaryModel {
  return {
    key: 'reference-morocco',
    label: 'Reference: Souss-Massa, Morocco',
    captured_at_utc: '2026-10-31T12:00:00+00:00',
    status: 'partial',
    scenario_id: 'sc-test',
    ...overrides,
  };
}

export function demoListFixture(summaries: DemoSnapshotSummaryModel[]) {
  return { version: 1, snapshots: summaries };
}

export function demoFileFixture(
  detail: ScenarioDetailFixture,
  overrides: Partial<DemoSnapshotFileModel> = {},
): DemoSnapshotFileModel {
  return {
    snapshot_version: 1,
    key: 'reference-morocco',
    label: 'Reference: Souss-Massa, Morocco',
    captured_at_utc: '2026-10-31T12:00:00+00:00',
    detail,
    ...overrides,
  };
}
