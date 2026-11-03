import { expect, test } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import {
  completeDetail,
  created,
  demoFile,
  demoList,
  partialAiDetail,
  runningDetail,
} from './fixtures';

const APP_URL = pathToFileURL(
  path.resolve(process.cwd(), 'dist', 'index.html'),
).href;

test('runs form → progress → results against a mocked backend', async ({
  page,
}) => {
  await page.route('**/v1/scenarios', (route) =>
    route.fulfill({ status: 202, json: created }),
  );
  let polls = 0;
  await page.route('**/v1/scenarios/sc-e2e', (route) => {
    polls += 1;
    return route.fulfill({ json: polls < 2 ? runningDetail : completeDetail });
  });

  await page.goto(`${APP_URL}#/new`);
  await page.getByRole('button', { name: 'Evidence & indicators' }).click();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByText('Analysis running')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByText('Rainfall · SPI (CHIRPS)')).toBeVisible();
  await expect(page.getByText('-0.517', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Report' }).click();
  await expect(page.getByRole('heading', { name: 'Report' })).toBeVisible();
  await expect(page.getByText('AI-generated narrative')).toBeVisible();
});

test('shows mixed authorship for ai-partial reports', async ({ page }) => {
  await page.route('**/v1/scenarios', (route) =>
    route.fulfill({ status: 202, json: created }),
  );
  await page.route('**/v1/scenarios/sc-e2e', (route) =>
    route.fulfill({ json: partialAiDetail }),
  );

  await page.goto(`${APP_URL}#/new`);
  await page.getByRole('button', { name: 'Evidence & indicators' }).click();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible({
    timeout: 15000,
  });
  await expect(
    page.getByText('AI report: 3/4 statements model-written (validated)'),
  ).toBeVisible();
  await expect(page.getByText('Why 1 statement is platform-written')).toBeVisible();
  await page.getByText('Why 1 statement is platform-written').click();
  await expect(page.getByText('limitations[0]').first()).toBeVisible();
  await expect(page.getByText(/replaced \(/).first()).toBeVisible();
});

test('maps a typed backend failure to its message', async ({ page }) => {
  await page.route('**/v1/scenarios', (route) =>
    route.fulfill({
      status: 422,
      json: {
        detail: [{ loc: ['body', 'query'], msg: 'field required', type: 'missing' }],
      },
    }),
  );

  await page.goto(`${APP_URL}#/new`);
  await page.getByRole('button', { name: 'Evidence & indicators' }).click();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByText('field required')).toBeVisible();
});

test('opens a demo snapshot with its banner', async ({ page }) => {
  await page.route('**/v1/demo/snapshots', (route) =>
    route.fulfill({ json: demoList }),
  );
  await page.route('**/v1/demo/snapshots/*', (route) =>
    route.fulfill({ json: demoFile }),
  );

  await page.goto(`${APP_URL}#/demo`);
  await page.getByRole('button', { name: 'Open' }).click();
  await expect(page.getByText('Cached real-data snapshot')).toBeVisible();
  await expect(page.getByText(/Stored results, not a live run/)).toBeVisible();
  await expect(page.getByText('Rainfall · SPI (CHIRPS)')).toBeVisible();
});
