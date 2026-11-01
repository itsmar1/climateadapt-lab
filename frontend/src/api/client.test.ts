import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createScenario,
  deleteScenario,
  getDemoSnapshot,
  getScenario,
  listDemoSnapshots,
} from './client';
import { ApiError } from './errors';

import { mockFetch } from '../test/fixtures';

const CREATED = {
  version: 1,
  scenario_id: 'sc-1',
  job_id: 'job-1',
  status: 'queued',
  status_url: '/v1/jobs/job-1',
  scenario_url: '/v1/scenarios/sc-1',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function scenarioBody() {
  return {
    latitude: 30.43,
    longitude: -9.61,
    target_end_month: '2024-03',
    timescale_months: 3,
    reference_start_year: 1991,
    reference_end_year: 2020,
    min_reference_years: 30,
    land_fallback_max_km: 15,
    indicators: ['chirps_spi'] as ('chirps_spi')[],
    query: 'deficit irrigation scheduling',
    top_k: 5,
    exclude_reference: true,
    crop: 'wheat',
    has_water_source: true,
    has_irrigation_equipment: true,
    production_system: 'irrigated' as const,
    season: '2024-03',
  };
}

describe('client', () => {
  it('posts the scenario body to the collection URL', async () => {
    const fetchMock = mockFetch([{ body: CREATED, status: 202 }]);
    vi.stubGlobal('fetch', fetchMock);

    const body = scenarioBody();
    const created = await createScenario(body);

    expect(created.scenario_id).toBe('sc-1');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [request] = fetchMock.mock.calls[0] as [Request];
    expect(request.url).toBe('http://127.0.0.1:8000/v1/scenarios');
    expect(request.method).toBe('POST');
    expect(await request.json()).toMatchObject(body);
  });

  it('maps typed error bodies to ApiError codes', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch([
        {
          body: {
            detail: [{ loc: [], msg: 'Unknown scenario id.', type: 'scenario_not_found' }],
          },
          status: 404,
        },
      ]),
    );

    const failure = await getScenario('missing').then(
      () => null,
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(ApiError);
    const apiError = failure as ApiError;
    expect(apiError.code).toBe('scenario_not_found');
    expect(apiError.status).toBe(404);
    expect(apiError.message).toContain('unknown or was deleted');
  });

  it('maps transport failures to network-error', async () => {
    vi.stubGlobal('fetch', mockFetch([new TypeError('fetch failed')]));

    const failure = await getScenario('sc-1').then(
      () => null,
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe('network-error');
  });

  it('rejects unknown contract versions', async () => {
    vi.stubGlobal('fetch', mockFetch([{ body: { ...CREATED, version: 999 }, status: 202 }]));

    const failure = await createScenario(scenarioBody()).then(
      () => null,
      (error: unknown) => error,
    );
    expect((failure as ApiError).code).toBe('unsupported-version');
  });

  it('lists demo snapshots with the version gate', async () => {
    const fetchMock = mockFetch([
      { body: { version: 1, snapshots: [] }, status: 200 },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    const page = await listDemoSnapshots();
    expect(page.snapshots).toEqual([]);
    const [request] = fetchMock.mock.calls[0] as [Request];
    expect(request.url).toBe('http://127.0.0.1:8000/v1/demo/snapshots');
  });

  it('fetches one demo snapshot by key', async () => {
    const fetchMock = mockFetch([{ body: { key: 'a-b_1' }, status: 200 }]);
    vi.stubGlobal('fetch', fetchMock);

    await getDemoSnapshot('a-b_1');
    const [request] = fetchMock.mock.calls[0] as [Request];
    expect(request.url).toBe('http://127.0.0.1:8000/v1/demo/snapshots/a-b_1');
  });

  it('treats a 204 delete as success', async () => {
    const fetchMock = mockFetch([{ status: 204 }]);
    vi.stubGlobal('fetch', fetchMock);

    await expect(deleteScenario('sc-1')).resolves.toBeUndefined();
    const [request] = fetchMock.mock.calls[0] as [Request];
    expect(request.url).toBe('http://127.0.0.1:8000/v1/scenarios/sc-1');
    expect(request.method).toBe('DELETE');
  });
});
