/**
 * Typed API client (openapi-fetch over types generated from docs/openapi.json
 * by `npm run gen:api`). Every function either returns typed data or throws
 * an ApiError carrying the backend's stable `type` code.
 */

import createClient from 'openapi-fetch';
import type { components, paths } from './schema';
import { ApiError, isAbortError, parseApiError } from './errors';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const SCENARIO_API_VERSION = 1;

const raw = createClient<paths>({
  baseUrl: API_BASE_URL,
  // Resolve fetch per call: openapi-fetch otherwise captures globalThis.fetch at
  // import time, which would make the transport unmockable. Production behavior
  // is unchanged (the global fetch is still used).
  fetch: (input) => globalThis.fetch(input),
});

export type AgentScenario = components['schemas']['AgentScenario'];
export type ScenarioCreated = components['schemas']['ScenarioCreated'];
export type ScenarioDetail = components['schemas']['ScenarioDetail'];
export type ScenarioList = components['schemas']['ScenarioList'];
export type JobStatus = components['schemas']['JobStatus'];
export type BundleIndicatorResult =
  components['schemas']['BundleIndicatorResult'];

const REQUEST_TIMEOUT_MS = 30000;

function checkVersion(data: unknown): void {
  if (typeof data !== 'object' || data === null || !('version' in data)) {
    return;
  }
  const version = (data as { version?: unknown }).version;
  if (version !== undefined && version !== SCENARIO_API_VERSION) {
    throw new ApiError('unsupported-version', 200);
  }
}

async function call<T>(
  run: (signal: AbortSignal) => Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let outcome: { data?: T; error?: unknown; response: Response };
  try {
    outcome = await run(AbortSignal.timeout(REQUEST_TIMEOUT_MS));
  } catch (error: unknown) {
    if (isAbortError(error)) {
      throw new ApiError('request-timeout', 0);
    }
    throw new ApiError('network-error', 0);
  }
  if (outcome.data !== undefined) {
    return outcome.data;
  }
  throw parseApiError(outcome.response.status, outcome.error);
}

export function createScenario(body: AgentScenario): Promise<ScenarioCreated> {
  return call((signal) => raw.POST('/v1/scenarios', { body, signal })).then((data) => {
    checkVersion(data);
    return data;
  });
}

export function getScenario(scenarioId: string): Promise<ScenarioDetail> {
  return call((signal) =>
    raw.GET('/v1/scenarios/{scenario_id}', {
      params: { path: { scenario_id: scenarioId } },
      signal,
    }),
  ).then((data) => {
    checkVersion(data);
    return data;
  });
}

export function listScenarios(limit = 20, offset = 0): Promise<ScenarioList> {
  return call((signal) =>
    raw.GET('/v1/scenarios', { params: { query: { limit, offset } }, signal }),
  ).then((data) => {
    checkVersion(data);
    return data;
  });
}

export async function deleteScenario(scenarioId: string): Promise<void> {
  try {
    const { error, response } = await raw.DELETE('/v1/scenarios/{scenario_id}', {
      params: { path: { scenario_id: scenarioId } },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (response.ok) {
      return;
    }
    throw parseApiError(response.status, error);
  } catch (error: unknown) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (isAbortError(error)) {
      throw new ApiError('request-timeout', 0);
    }
    throw new ApiError('network-error', 0);
  }
}

export function getJob(jobId: string): Promise<JobStatus> {
  return call((signal) =>
    raw.GET('/v1/jobs/{job_id}', { params: { path: { job_id: jobId } }, signal }),
  );
}
