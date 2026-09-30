/**
 * F5's gate against the deployed site (spec §14 F5, AC-F-10, D-F-8): one origin for the frontend
 * and the API with no CORS, the clean demo dataset, the brief, an approval, and the mock sources'
 * honest caption. `@clean` tests only read; the `@write` test records one approval.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, test, type APIRequestContext } from '@playwright/test';

import { COPY } from '../../src/copy';

test.describe.configure({ mode: 'serial' });

/** §3's payload hashes at 2026-09-18 on the clean dataset, and the pinned fingerprint. */
const PAYLOAD_HASHES: Record<string, string> = {
  'CUST-007': 'e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946',
  'CUST-025': '08c99ced40996611c8f7bb4ea48e918fabe0e9cd68390122d0f86faa50738770',
  'CUST-036': 'a6240ac1edd4890724568adc7a8bd8f99add305638b9dcb179429ae67d06b637',
};
const FINGERPRINT = '1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00';

const GOLDEN = readFileSync(
  resolve(import.meta.dirname, '../../../tests/golden/vs01_cust007_brief.txt'),
  'utf8',
);

interface BriefBody {
  payload_hash: string;
  decision_status: string;
  narrative: string;
  payload: { scope: { layer1_fingerprint: string } };
}

async function json<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(path);
  expect(response.status(), path).toBe(200);
  return (await response.json()) as T;
}

/** The brief ids at 2026-09-18, by customer, read from the API itself. */
async function briefIds(request: APIRequestContext): Promise<Record<string, string>> {
  const body = await json<{
    total: number;
    items: { customer_source_id: string; brief_ids: string[] }[];
  }>(request, '/api/v1/risk/assessments?as_of=2026-09-18&limit=500&offset=0');
  expect(body.total).toBe(50);
  return Object.fromEntries(
    body.items
      .filter((item) => item.brief_ids.length > 0)
      .map((item) => [item.customer_source_id, item.brief_ids[0] as string]),
  );
}

const chainLength = async (request: APIRequestContext, id: string) =>
  (await json<{ items: unknown[] }>(request, `/api/v1/risk/briefs/${id}/decisions`)).items.length;

test('serves the frontend and the API on one origin, without CORS @clean', async ({
  request,
  page,
}) => {
  const health = await request.get('/api/v1/health', {
    headers: { Origin: 'https://example.invalid' },
  });
  expect(health.status()).toBe(200);
  expect(await health.json()).toMatchObject({ status: 'healthy', checks: { database: 'ok' } });
  expect(health.headers()['access-control-allow-origin']).toBeUndefined();

  const openapi = await json<{ paths: Record<string, unknown> }>(request, '/openapi.json');
  expect(Object.keys(openapi.paths)).toContain('/api/v1/health');
  expect((await request.get('/docs')).status()).toBe(200);

  // A deep link is the app's own page, not a 404.
  const deep = await request.get('/classic/inbox');
  expect(deep.status()).toBe(200);
  expect(await deep.text()).toContain('<div id="root"></div>');

  await page.goto('/?as_of=2026-09-18');
  await expect(page.getByTestId('office')).toHaveAttribute('data-world', 'ready', {
    timeout: 30_000,
  });
  await expect(page.getByRole('banner')).toContainText('API healthy');
});

test('holds the clean demo dataset: three briefs, the pinned hashes, no decision @clean', async ({
  request,
}) => {
  const ids = await briefIds(request);
  expect(Object.keys(ids).sort()).toEqual(Object.keys(PAYLOAD_HASHES));
  for (const [customer, id] of Object.entries(ids)) {
    const brief = await json<BriefBody>(request, `/api/v1/risk/briefs/${id}`);
    expect(brief.payload_hash, customer).toBe(PAYLOAD_HASHES[customer]);
    expect(brief.payload.scope.layer1_fingerprint).toBe(FINGERPRINT);
    expect(brief.decision_status, customer).toBe('PENDING');
    expect(await chainLength(request, id), customer).toBe(0);
    if (customer === 'CUST-007') expect(brief.narrative).toBe(GOLDEN);
  }
});

test('shows the inbox, and says the mock sources run in local mode only @clean', async ({
  page,
}) => {
  await page.goto('/classic/inbox?as_of=2026-09-18');
  const rows = page.getByTestId('inbox-row');
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText('CRITICAL·EXECUTIVE');
  await expect(rows.nth(0)).toContainText('CUST-007');

  for (const source of ['odoo_mock', 'rest_mock']) {
    await page.goto(`/classic/agents/${source}`);
    const health = page.getByRole('region', { name: 'Health check' });
    await expect(health).toContainText('unhealthy');
    await expect(health).toContainText(COPY.mockSourceHostedOnly);
  }
  await page.goto('/classic/agents/csv_demo');
  await expect(page.getByRole('region', { name: 'Health check' })).toContainText('healthy');
});

test('records an approval of CUST-007 @write', async ({ page, request }) => {
  const id = (await briefIds(request))['CUST-007'] ?? '';
  const before = await chainLength(request, id);

  await page.goto(`/classic/briefs/${id}`);
  const form = page.getByRole('form', { name: 'Record a decision' });
  await form.locator('label', { hasText: 'Approve' }).click();
  await form.getByLabel(/^Note/).fill('Hosted smoke test.');
  await form.getByLabel('Your name').fill('Hosted smoke');
  const posted = page.waitForResponse(
    (response) => response.request().method() === 'POST' && response.url().endsWith('/decision'),
  );
  await form.getByRole('button', { name: 'Record decision' }).click();
  expect((await posted).status()).toBe(201);

  await expect(page.getByRole('region', { name: 'Decision chain' })).toContainText(
    'APPROVEDby Hosted smoke',
  );
  expect(await chainLength(request, id)).toBe(before + 1);
});
