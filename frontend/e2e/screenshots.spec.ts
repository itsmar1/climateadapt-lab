import { expect, test } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { created, partialDetail, runningDetail } from './fixtures';

const APP_URL = pathToFileURL(
  path.resolve(process.cwd(), 'dist', 'index.html'),
).href;
const SHOT_DIR = path.resolve(process.cwd(), 'test-results', 'screenshots');

/**
 * README/video screenshots (P20). Mocked backend, real bundle; the chosen
 * shots are copied to docs/screenshots/ by hand after the run. Tile pixels
 * depend on sandbox egress — see the P20 report for what actually rendered.
 */
test('capture README and video screenshots', async ({ page }) => {
  await page.route('**/v1/scenarios', (route) =>
    route.fulfill({ status: 202, json: created }),
  );
  await page.route('**/v1/scenarios/sc-e2e', (route) =>
    route.fulfill({ json: runningDetail }),
  );

  await page.goto(APP_URL);
  await expect(page.locator('.geo-map')).toBeVisible();
  await page.screenshot({ path: path.join(SHOT_DIR, '01-form-map.png') });

  await page.getByRole('button', { name: 'Trøndelag, Norway' }).click();
  await expect(page.getByText(/outside the CHIRPS band/)).toBeVisible();
  await page.screenshot({ path: path.join(SHOT_DIR, '02-outside-band.png') });

  await page.getByRole('button', { name: 'Morocco (reference)' }).click();
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByText('Analysis running')).toBeVisible();
  await page.screenshot({ path: path.join(SHOT_DIR, '03-progress.png') });

  // Late-registered routes win: the next poll lands the partial result.
  await page.route('**/v1/scenarios/sc-e2e', (route) =>
    route.fulfill({ json: partialDetail }),
  );
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible({
    timeout: 15000,
  });
  await page.screenshot({ path: path.join(SHOT_DIR, '04-results.png') });
  await page
    .locator('#report')
    .screenshot({ path: path.join(SHOT_DIR, '05-report.png') });
});
