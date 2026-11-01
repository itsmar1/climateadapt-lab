// @vitest-environment node
/**
 * Contract test: the routes and fields this app uses must exist in the
 * backend's OpenAPI contract, and the generated types must cover them.
 * Run `npm run gen:api` after any backend route change.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

interface OpenApiDocument {
  paths: Record<string, Record<string, unknown>>;
  components: { schemas: Record<string, { required?: string[]; properties?: object }> };
}

function loadSpec(): OpenApiDocument {
  const file = path.resolve(process.cwd(), '..', 'docs', 'openapi.json');
  return JSON.parse(fs.readFileSync(file, 'utf-8')) as OpenApiDocument;
}

describe('backend contract', () => {
  it('exposes the scenario and job routes the app calls', () => {
    const spec = loadSpec();
    expect(Object.keys(spec.paths)).toContain('/v1/scenarios');
    expect(Object.keys(spec.paths)).toContain('/v1/scenarios/{scenario_id}');
    expect(Object.keys(spec.paths)).toContain('/v1/jobs/{job_id}');
    expect(Object.keys(spec.paths)).toContain('/v1/demo/snapshots');
    expect(Object.keys(spec.paths)).toContain('/v1/demo/snapshots/{key}');
    expect(spec.paths['/v1/scenarios']).toHaveProperty('post');
    expect(spec.paths['/v1/scenarios']).toHaveProperty('get');
    expect(spec.paths['/v1/scenarios/{scenario_id}']).toHaveProperty('get');
    expect(spec.paths['/v1/scenarios/{scenario_id}']).toHaveProperty('delete');
    expect(spec.paths['/v1/jobs/{job_id}']).toHaveProperty('get');
    expect(spec.paths['/v1/demo/snapshots']).toHaveProperty('get');
    expect(spec.paths['/v1/demo/snapshots/{key}']).toHaveProperty('get');
  });

  it('keeps the fields the results page renders', () => {
    const spec = loadSpec();
    const schemas = spec.components.schemas;
    for (const name of [
      'AgentScenario',
      'ScenarioCreated',
      'ScenarioDetail',
      'ScenarioList',
      'JobStatus',
      'BundleIndicatorResult',
      'EnvironmentalBundleResponse',
      'DemoSnapshotFile',
      'DemoSnapshotList',
      'DemoSnapshotSummary',
    ]) {
      expect(schemas, name).toHaveProperty(name);
    }
    const detail = schemas['ScenarioDetail']?.required ?? [];
    for (const field of [
      'status',
      'bundle',
      'ranking',
      'report',
      'trace',
      'problems',
      'warnings',
    ]) {
      expect(detail, field).toContain(field);
    }
    const entry = schemas['BundleIndicatorResult'];
    for (const field of ['indicator', 'status']) {
      expect(entry?.required ?? [], field).toContain(field);
    }
    expect(Object.keys(entry?.properties ?? {}), 'result').toContain('result');
  });

  it('keeps the generated types in sync with the contract file', () => {
    const generated = fs.readFileSync(
      path.resolve(process.cwd(), 'src', 'api', 'schema.d.ts'),
      'utf-8',
    );
    for (const token of [
      '"/v1/scenarios"',
      '"/v1/scenarios/{scenario_id}"',
      '"/v1/jobs/{job_id}"',
      '"/v1/demo/snapshots"',
      '"/v1/demo/snapshots/{key}"',
      'AgentScenario',
      'BundleIndicatorResult',
      'ScenarioDetail',
      'DemoSnapshotFile',
    ]) {
      expect(generated, token).toContain(token);
    }
  });
});
