import { expect, test } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { created, partialDetail } from './fixtures';

const APP_URL = pathToFileURL(
  path.resolve(process.cwd(), 'dist', 'index.html'),
).href;

test('presets set coordinates and flag the outside-band point', async ({
  page,
}) => {
  await page.goto(APP_URL);
  await expect(page.locator('.geo-map')).toBeVisible();

  await page.getByRole('button', { name: 'Trøndelag, Norway' }).click();
  await expect(page.getByLabel('Latitude')).toHaveValue('63.4');
  await expect(page.getByLabel('Longitude')).toHaveValue('10.4');
  await expect(page.getByText(/outside the CHIRPS band/)).toBeVisible();
  await expect(page.getByText('outside_coverage')).toBeVisible();

  await page.getByRole('button', { name: 'Morocco (reference)' }).click();
  await expect(page.getByLabel('Latitude')).toHaveValue('30.43');
  await expect(page.getByText(/outside the CHIRPS band/)).toHaveCount(0);
});

test('clicking the real map writes coordinates back to the inputs', async ({
  page,
}) => {
  await page.goto(APP_URL);
  const map = page.locator('.geo-map');
  await expect(map).toBeVisible();

  // Off-centre click (clear of the centred marker and corner controls):
  // the picked point must be a finite in-range pair at two decimals.
  await map.click({ position: { x: 260, y: 210 } });
  const lat = await page.getByLabel('Latitude').inputValue();
  const lon = await page.getByLabel('Longitude').inputValue();
  expect(lat).toMatch(/^-?\d+\.\d{2}$/);
  expect(lon).toMatch(/^-?\d+\.\d{2}$/);
  expect(Number(lat)).toBeGreaterThanOrEqual(-90);
  expect(Number(lat)).toBeLessThanOrEqual(90);
  expect(Number(lon)).toBeGreaterThanOrEqual(-180);
  expect(Number(lon)).toBeLessThanOrEqual(180);
  expect([lat, lon]).not.toEqual(['30.43', '-9.61']);
  await expect(page.locator('.geo-dot-request')).toHaveCount(1);
});

test('results map marks the requested and actually-used points', async ({
  page,
}) => {
  await page.route('**/v1/scenarios', (route) =>
    route.fulfill({ status: 202, json: created }),
  );
  await page.route('**/v1/scenarios/sc-e2e', (route) =>
    route.fulfill({ json: partialDetail }),
  );

  await page.goto(APP_URL);
  await page.getByRole('button', { name: 'Run analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible({
    timeout: 15000,
  });

  await expect(page.getByText('Platform fallback report')).toBeVisible();
  await expect(page.locator('.geo-dot-request')).toHaveCount(1);
  await expect(page.locator('.geo-dot-used')).toHaveCount(1);
  await expect(page.getByText(/7\.8 km from requested/)).toBeVisible();
  await expect(
    page.getByText(/Limitations & provenance \(\d+\)/).first(),
  ).toBeVisible();

  // Problems stay collapsed under their grouped summary until opened.
  const summary = page.getByText(/Why this is the platform fallback/);
  await expect(summary).toBeVisible();
  await expect(summary).toContainText('3 problems in 2 groups');
  await expect(page.getByText('provider-auth')).toBeHidden();
  await summary.click();
  await expect(page.getByText('provider-auth')).toBeVisible();
  await expect(page.getByText('retrieval-empty')).toBeVisible();

  // Severity guard: the only "severity" on the page is the footer's denial.
  const body = await page.locator('body').innerText();
  const scrubbed = body.replace(
    /No severity\s+scores are shown anywhere in this app;/,
    '',
  );
  expect(scrubbed).not.toMatch(
    /\bsevere\b|\bseverity\b|extreme drought|drought categor/i,
  );
});
