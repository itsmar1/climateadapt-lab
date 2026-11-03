import { expect, test } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import {
  completeDetail,
  created,
  demoFile,
  demoList,
  runningDetail,
} from './fixtures';

const APP_URL = pathToFileURL(
  path.resolve(process.cwd(), 'dist', 'index.html'),
).href;

const historyList = {
  version: 1,
  items: [
    {
      scenario_id: 'sc-e2e',
      status: 'complete',
      latitude: 30.43,
      longitude: -9.61,
      target_end_month: '2024-03',
      query: 'deficit irrigation scheduling',
      created_at: '2026-10-31T00:00:00+00:00',
      updated_at: '2026-10-31T00:01:00+00:00',
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

/**
 * Console guard (P26): walk every route and fail on any console error or
 * uncaught page error. Tile pixels may be blank offline, but no JS error
 * may accompany them.
 */
test('no console errors or page errors across routes', async ({ page }) => {
  const problems: string[] = [];
  page.on('console', (message) => {
    // Resource-load failures are attributed with URLs below; anything else
    // logged as an error is a real problem.
    if (
      message.type() === 'error' &&
      !message.text().startsWith('Failed to load resource')
    ) {
      problems.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    problems.push(String(error));
  });
  page.on('requestfailed', (request) => {
    // OSM tile egress is blocked in sandboxes (see the P20 report); every
    // other failed request — app assets included — is a real problem.
    if (new URL(request.url()).hostname !== 'tile.openstreetmap.org') {
      problems.push(
        `requestfailed: ${request.url()} ${request.failure()?.errorText ?? ''}`,
      );
    }
  });

  await page.route('**/v1/demo/snapshots', (route) =>
    route.fulfill({ json: demoList }),
  );
  await page.route('**/v1/demo/snapshots/*', (route) =>
    route.fulfill({ json: demoFile }),
  );
  await page.route('**/v1/scenarios', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 202, json: created })
      : route.fulfill({ json: historyList }),
  );
  await page.route('**/v1/scenarios?*', (route) =>
    route.fulfill({ json: historyList }),
  );
  let polls = 0;
  await page.route('**/v1/scenarios/sc-e2e', (route) => {
    polls += 1;
    return route.fulfill({ json: polls < 2 ? runningDetail : completeDetail });
  });

  await page.goto(APP_URL);
  await expect(page.getByTestId('overview-counts')).toBeVisible();

  await page.goto(`${APP_URL}#/new`);
  for (const step of [
    'Crop & system',
    'Time & reference',
    'Evidence & indicators',
    'Location',
  ]) {
    await page.getByRole('button', { name: step, exact: true }).click();
  }
  await page.getByRole('button', { name: 'Evidence & indicators' }).click();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible({
    timeout: 15000,
  });
  for (const tab of [
    'Evidence & options',
    'Report',
    'Provenance & methods',
    'Indicators',
  ]) {
    await page.getByRole('tab', { name: tab }).click();
  }

  await page.goto(`${APP_URL}#/scenarios`);
  await expect(page.getByText('sc-e2e').first()).toBeVisible();

  await page.goto(`${APP_URL}#/demo`);
  await expect(page.getByRole('button', { name: 'Open' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Open' }).first().click();
  await expect(page.getByText('Cached real-data snapshot')).toBeVisible();

  expect(problems).toEqual([]);
});
