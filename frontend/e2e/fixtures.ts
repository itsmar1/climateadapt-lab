/**
 * Compact mocked-backend payloads for the Playwright suite. Deliberately
 * independent of src/test/fixtures.ts (that module imports vitest, which must
 * not load under the Playwright runner). Shapes mirror the API contract.
 */

export const created = {
  version: 1,
  scenario_id: 'sc-e2e',
  job_id: 'job-e2e',
  status: 'queued',
  status_url: '/v1/jobs/job-e2e',
  scenario_url: '/v1/scenarios/sc-e2e',
};

const scenarioInput = {
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
};

function baseDetail(status: string) {
  return {
    version: 1,
    scenario_id: 'sc-e2e',
    job_id: 'job-e2e',
    status,
    created_at: '2026-10-31T00:00:00+00:00',
    updated_at: '2026-10-31T00:01:00+00:00',
    scenario: scenarioInput,
    bundle: null,
    ranking: null,
    report: null,
    trace: null,
    problems: [],
    warnings: [],
  };
}

export const runningDetail = baseDetail('running');

export const completeDetail = {
  ...baseDetail('complete'),
  bundle: {
    indicator: 'environmental_bundle',
    latitude: 30.43,
    longitude: -9.61,
    target_end_month: '2024-03',
    timescale_months: 3,
    reference_start_year: 1991,
    reference_end_year: 2020,
    entries: [
      {
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
          reference_years_excluded: [],
          reference_spi_mean: 0.012,
          reference_spi_std: 1.004,
          reference_start_year: 1991,
          reference_end_year: 2020,
          point_on_cell_boundary: false,
          target_in_reference_period: false,
          citation: 'Funk et al. (2015).',
          doi: '10.1038/sdata.2015.66',
          license_note: 'Free for research.',
          limitations: ['Precipitation only; not a drought verdict.'],
        },
      },
    ],
  },
  ranking: {
    catalog_version: 1,
    scenario: {},
    ranked: [
      {
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
        unknowns: [],
        evidence: [],
        benefit: 'unknown',
        cost: 'unknown',
        risk: 'unknown',
      },
    ],
    excluded: [],
    warnings: [],
    limitations: ['E2E ranking limitation.'],
  },
  report: {
    schema_version: 1,
    generator: 'fake:e2e-model',
    fallback: false,
    fallback_note: null,
    summary: {
      text: 'E2E summary.',
      evidence_ids: [],
      tool_output_ids: ['bundle'],
      numbers: [],
    },
    environmental_findings: [
      {
        text: 'E2E finding.',
        evidence_ids: [],
        tool_output_ids: ['chirps_spi'],
        numbers: [],
      },
    ],
    evidence: [],
    ranked_recommendations: [],
    excluded_options: [],
    limitations: ['E2E report limitation.'],
    assumptions: [],
    data_coverage: {
      text: 'E2E coverage.',
      evidence_ids: [],
      tool_output_ids: ['bundle'],
      numbers: [],
    },
    provenance_refs: ['bundle'],
  },
};

const tempEntryWithFallback = {
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
      distance_km: 7.8,
    },
    citation: 'Muñoz-Sabater et al. (2021).',
    doi: '10.5194/essd-13-4349-2021',
    license_note: 'Copernicus licence.',
    limitations: ['Reanalysis, not station data.'],
  },
};

/** Partial run: fallback report, grouped problems, one used land fallback. */
export const partialDetail = {
  ...baseDetail('partial'),
  bundle: {
    ...completeDetail.bundle,
    entries: [...completeDetail.bundle.entries, tempEntryWithFallback],
  },
  ranking: completeDetail.ranking,
  report: {
    ...completeDetail.report,
    generator: 'deterministic-fallback',
    fallback: true,
    fallback_note: 'E2E fallback note.',
  },
  problems: [
    '[provider-auth] No model key configured; serving deterministic fallback.',
    '[provider-auth] Draft call skipped (no key).',
    '[retrieval-empty] No passages retrieved.',
  ],
  warnings: [],
};

/** Mixed run: ai-partial report with one replaced limitation. */
export const partialAiDetail = {
  ...baseDetail('complete'),
  bundle: completeDetail.bundle,
  ranking: completeDetail.ranking,
  report: {
    ...completeDetail.report,
    acceptance: 'ai-partial',
    statement_origins: {
      summary: 'model',
      'environmental_findings[0]': 'model',
      'limitations[0]': 'platform',
      data_coverage: 'model',
    },
    replaced_statements: { 'limitations[0]': ['undeclared-number'] },
    dropped_statements: {},
  },
  problems: [],
  warnings: [
    '[composite] Base: repair (4 problems); 1 replaced, 0 dropped (undeclared-number); 3 of 4 model-written.',
  ],
};

export const demoList = {
  version: 1,
  snapshots: [
    {
      key: 'e2e-snapshot',
      label: 'E2E snapshot',
      captured_at_utc: '2026-10-31T12:00:00+00:00',
      status: 'complete',
      scenario_id: 'sc-e2e',
    },
  ],
};

export const demoFile = {
  snapshot_version: 1,
  key: 'e2e-snapshot',
  label: 'E2E snapshot',
  captured_at_utc: '2026-10-31T12:00:00+00:00',
  detail: completeDetail,
};
