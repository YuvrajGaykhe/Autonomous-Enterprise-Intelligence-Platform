/**
 * F1's gate (spec §14): the HUD shows `/health` from the isolated API.
 */

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

function environment(name: string): string {
  const value = process.env[name];
  if (value === undefined) throw new Error(`${name} is not set: run through playwright test`);
  return value;
}

const baseUrl = () => environment('AICEOHQ_E2E_BASE_URL');
const apiUrl = () => environment('AICEOHQ_E2E_API_URL');

test('the HUD shows GET /api/v1/health from the isolated API', async ({ page, request }) => {
  const direct = await request.get(`${apiUrl()}/api/v1/health`);
  expect(direct.status()).toBe(200);
  const expected = (await direct.json()) as { status: string; version: string };

  const healthResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/health'),
  );
  await page.goto(`${baseUrl()}/classic`);
  const response = await healthResponse;
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual(expected);

  await expect(page.getByRole('link', { name: 'AI CEO HQ' })).toBeVisible();
  const light = page.getByTestId('health-light');
  await expect(light).toContainText(`API ${expected.status}`);
  await expect(light).toContainText(`database ok · v${expected.version}`);

  const requestId = response.headers()['x-request-id'];
  expect(requestId).toMatch(/^[0-9a-f]{32}$/);
  await expect(
    page.getByRole('region', { name: 'System status' }).getByText(requestId ?? ''),
  ).toBeVisible();
});

test('/ opens Classic view with the default as_of', async ({ page }) => {
  await page.goto(`${baseUrl()}/`);

  await expect(page).toHaveURL(/\/classic$/);
  await expect(page.getByLabel('as_of date')).toHaveValue('2026-09-18');
});

test('the Classic overview has no serious or critical accessibility violations', async ({
  page,
}) => {
  await page.goto(`${baseUrl()}/classic`);
  await expect(page.getByTestId('health-light')).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter(
    (violation) => violation.impact === 'serious' || violation.impact === 'critical',
  );
  expect(blocking.map((violation) => violation.id)).toEqual([]);
});
