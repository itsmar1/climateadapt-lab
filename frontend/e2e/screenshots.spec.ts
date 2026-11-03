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
const SHOT_DIR = path.resolve(process.cwd(), 'test-results', 'screenshots');

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
    {
      scenario_id: 'sc-trondelag',
      status: 'partial',
      latitude: 63.43,
      longitude: 10.4,
      target_end_month: '2024-03',
      query: 'rainfed barley options',
      created_at: '2026-10-30T00:00:00+00:00',
      updated_at: '2026-10-30T00:01:00+00:00',
    },
  ],
  total: 2,
  limit: 20,
  offset: 0,
};

/**
 * README/video screenshots (P26 redesign). Mocked backend, real bundle; the
 * chosen shots are copied to docs/screenshots/ by hand after the run. Tile
 * pixels depend on sandbox egress — see the P26 report for what rendered.
 */
test('capture overview, workspace, and history screenshots', async ({
  page,
}) => {
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
  await page.screenshot({ path: path.join(SHOT_DIR, '01-overview.png') });

  await page.goto(`${APP_URL}#/new`);
  await expect(page.locator('.geo-map')).toBeVisible();
  await page.screenshot({ path: path.join(SHOT_DIR, '02-stepper.png') });

  await page.getByRole('button', { name: 'Evidence & indicators' }).click();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible({
    timeout: 15000,
  });
  await page.screenshot({ path: path.join(SHOT_DIR, '03-results-tabs.png') });

  await page.getByRole('tab', { name: 'Report' }).click();
  await expect(page.getByText('AI report accepted')).toBeVisible();
  await page.screenshot({ path: path.join(SHOT_DIR, '04-report-accepted.png') });

  await page.goto(`${APP_URL}#/scenarios`);
  await expect(page.getByText('sc-trondelag')).toBeVisible();
  await page.screenshot({ path: path.join(SHOT_DIR, '05-history.png') });
});
