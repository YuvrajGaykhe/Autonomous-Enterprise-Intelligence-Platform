/**
 * F2's gate (spec §14, AC-F-5, AC-F-6, AC-F-12): Classic view against the real API over the
 * isolated `<database>_frontend_e2e`, which the global setup recreated and assessed at 2026-09-18.
 *
 * The tests run in order because they share that database: the screenshots first, while it is
 * clean; then the inbox, the brief, the decisions and their refusals; then Auto and an API that is
 * down. Nothing here opens the development database.
 */

import { expect, type Locator, type Page } from '@playwright/test';

import {
  GOLDEN,
  apiUrl,
  baseUrl,
  briefIds,
  chainOf,
  expectAccessible,
  fontsReady,
  statusOf,
  test,
} from './support';

test.describe.configure({ mode: 'serial' });

const AGENT_IDS = [
  'csv_demo',
  'odoo_mock',
  'rest_mock',
  'memory',
  'linker',
  'signals',
  'sales',
  'support',
  'reconciler',
  'brief-writer',
  'ceo',
];

let briefs: Record<string, string>;

test.beforeAll(async ({ request }) => {
  briefs = await briefIds(request);
  expect(Object.keys(briefs).sort()).toEqual(['CUST-007', 'CUST-025', 'CUST-036']);
});

const brief = (customer: string) => `${baseUrl()}/classic/briefs/${briefs[customer] ?? ''}`;

async function inboxRows(page: Page): Promise<Locator> {
  const rows = page.getByTestId('inbox-row');
  await expect(rows.first()).toBeVisible();
  return rows;
}

async function openBrief(page: Page, customer: string): Promise<Locator> {
  await page.goto(brief(customer));
  await expect(page.getByRole('region', { name: 'Technical' })).toBeVisible();
  const form = page.getByRole('form', { name: 'Record a decision' });
  await expect(
    page.getByRole('region', { name: 'Decision chain' }).getByRole('status'),
  ).toHaveCount(0);
  return form;
}

async function decide(form: Locator, choice: 'Approve' | 'Reject', note: string, actor: string) {
  await form.locator('label', { hasText: choice }).click();
  await form.getByLabel(/^Note/).fill(note);
  await form.getByLabel('Your name').fill(actor);
}

function decisionPosted(page: Page) {
  return page.waitForResponse(
    (response) => response.request().method() === 'POST' && response.url().endsWith('/decision'),
  );
}

test.describe('screenshots of the clean database (§12.1)', () => {
  test('the Classic overview', async ({ page }) => {
    await page.goto(`${baseUrl()}/classic`);
    const status = page.getByRole('region', { name: 'System status' });
    await expect(status.getByText('ai-ceo-layer1')).toBeVisible();
    await expect(
      page.getByRole('list', { name: 'Staff directory' }).getByText('REST_MOCK_AGENT'),
    ).toBeVisible();
    await fontsReady(page);
    await expect(page).toHaveScreenshot('overview.png', {
      mask: [status.locator('dd').last()],
    });
  });

  test('the CEO inbox', async ({ page }) => {
    await page.goto(`${baseUrl()}/classic/inbox`);
    await inboxRows(page);
    await fontsReady(page);
    await expect(page).toHaveScreenshot('inbox.png');
  });

  test("CUST-007's brief", async ({ page }) => {
    await openBrief(page, 'CUST-007');
    await expect(
      page.getByRole('region', { name: 'Evidence: cited quotes' }).locator('blockquote'),
    ).toHaveCount(3);
    await fontsReady(page);
    await expect(page).toHaveScreenshot('brief-cust-007.png');
  });

  test('the MEMORY, RECONCILER_AGENT and CSV_DEMO_AGENT panels', async ({ page }) => {
    await page.goto(`${baseUrl()}/classic/agents/memory`);
    await expect(
      page.getByRole('region', { name: 'Snapshot' }).getByText(/^1d891b0b/),
    ).toBeVisible();
    await expect(
      page.getByRole('region', { name: 'Ingestion metrics' }).getByText('233'),
    ).toBeVisible();
    await fontsReady(page);
    await expect(page).toHaveScreenshot('agent-memory.png');

    await page.goto(`${baseUrl()}/classic/agents/reconciler`);
    await expect(page.getByRole('region', { name: 'Executive worthiness' })).toBeVisible();
    await fontsReady(page);
    await expect(page).toHaveScreenshot('agent-reconciler.png');

    await page.goto(`${baseUrl()}/classic/agents/csv_demo`);
    await expect(
      page.getByRole('region', { name: 'Latest ingestion runs' }).getByText('SUCCESS'),
    ).toBeVisible();
    await expect(
      page.getByRole('region', { name: 'Health check' }).getByText('healthy'),
    ).toBeVisible();
    await fontsReady(page);
    await expect(page).toHaveScreenshot('agent-csv-demo.png', { mask: [page.locator('time')] });
  });
});

test.describe('the inbox and the brief (AC-F-5)', () => {
  test('CUST-007 is pinned CRITICAL · EXECUTIVE, and CUST-025 and CUST-036 follow', async ({
    page,
  }) => {
    await page.goto(`${baseUrl()}/classic/inbox`);
    const rows = await inboxRows(page);

    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText('CRITICAL·EXECUTIVE');
    await expect(rows.nth(0)).toContainText('CUST-007');
    await expect(rows.nth(1)).toContainText('WATCH');
    await expect(rows.nth(1)).toContainText('CUST-025');
    await expect(rows.nth(2)).toContainText('CUST-036');
    for (const index of [0, 1, 2]) await expect(rows.nth(index)).toContainText('PENDING');
  });

  test('Run assessment at 2026-09-18 answers 200: already assessed, nothing written', async ({
    page,
  }) => {
    await page.goto(`${baseUrl()}/classic`);
    const posted = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && response.url().endsWith('/risk/assessments'),
    );
    await page.getByRole('banner').getByRole('button', { name: 'Run assessment' }).click();

    const response = await posted;
    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual({
      as_of: '2026-09-18',
      source_system: 'csv_demo',
    });
    await expect(page.getByRole('status', { name: 'Assessment run' })).toHaveText(
      'Already assessed at 2026-09-18: all 50 results existed, so nothing was written.',
    );
    await expect(page).toHaveURL(/\/classic\/inbox$/);
    await expect(await inboxRows(page)).toHaveCount(3);
  });

  test("CUST-007's brief is the golden brief, cited and linked", async ({ page }) => {
    await openBrief(page, 'CUST-007');

    await expect(page.getByRole('region', { name: 'Narrative' }).locator('pre')).toHaveText(
      GOLDEN,
      {
        useInnerText: false,
      },
    );
    const quotes = page
      .getByRole('region', { name: 'Evidence: cited quotes' })
      .locator('blockquote');
    await expect(quotes).toHaveCount(3);
    for (const text of await quotes.allTextContents()) {
      expect(GOLDEN).toContain(`: "${text.replace(/^“|”$/g, '')}"`);
    }
    await expect(page.getByRole('region', { name: 'Decision chain' })).toContainText(
      'No decisions recorded for this brief yet.',
    );

    await page
      .getByRole('region', { name: 'Evidence: documents' })
      .getByRole('button', { name: /^DOC-\d{3} \[/ })
      .first()
      .click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.locator('mark')).toHaveText('Meridian Textiles');
    await expectAccessible(page);
    await dialog.getByRole('button', { name: 'Close' }).click();
    await expect(dialog).toHaveCount(0);
  });
});

test.describe('decisions (AC-F-5, AC-F-6)', () => {
  test('approve CUST-007: the decision is recorded and the chain and status update', async ({
    page,
    request,
  }) => {
    const form = await openBrief(page, 'CUST-007');
    await decide(
      form,
      'Approve',
      'Pause the deal push until the tickets are resolved.',
      'E2E Owner',
    );

    const posted = decisionPosted(page);
    await form.getByRole('button', { name: 'Record decision' }).click();
    const response = await posted;

    expect(response.status()).toBe(201);
    const chain = page.getByRole('region', { name: 'Decision chain' });
    await expect(chain.getByText('①')).toBeVisible();
    await expect(chain).toContainText('APPROVEDby E2E Owner');
    await expect(page.locator('[data-decision-status]')).toHaveAttribute(
      'data-decision-status',
      'APPROVED',
    );
    const stored = await chainOf(request, briefs['CUST-007'] ?? '');
    expect(stored.map((item) => [item.decision, item.actor, item.supersedes_id])).toEqual([
      ['APPROVED', 'E2E Owner', null],
    ]);
    expect(await statusOf(request, briefs['CUST-007'] ?? '')).toBe('APPROVED');

    await page.goto(`${baseUrl()}/classic/inbox`);
    await expect((await inboxRows(page)).nth(0)).toContainText('APPROVED');
  });

  test('reject with supersede: ② supersedes ①, and the status is REJECTED', async ({
    page,
    request,
  }) => {
    const form = await openBrief(page, 'CUST-007');
    await decide(form, 'Reject', 'Superseded after review.', 'E2E Owner');

    const posted = decisionPosted(page);
    await form.getByRole('button', { name: 'Record decision' }).click();
    expect((await posted).status()).toBe(201);

    const chain = page.getByRole('region', { name: 'Decision chain' });
    await expect(chain.getByRole('link', { name: 'supersedes ①' })).toBeVisible();
    await expect(page.locator('[data-decision-status]')).toHaveAttribute(
      'data-decision-status',
      'REJECTED',
    );
    const stored = await chainOf(request, briefs['CUST-007'] ?? '');
    expect(stored).toHaveLength(2);
    expect(stored[1]?.supersedes_id).toBe(stored[0]?.id);
    expect(await statusOf(request, briefs['CUST-007'] ?? '')).toBe('REJECTED');
  });

  test('409 DECISION_CONFLICT: someone decided meanwhile; the note is kept; resubmit works', async ({
    page,
    request,
  }) => {
    const form = await openBrief(page, 'CUST-007');
    await expect(page.getByRole('region', { name: 'Decision chain' }).getByText('②')).toBeVisible();
    await decide(form, 'Approve', 'Written before the other reviewer.', 'E2E Owner');

    const head = (await chainOf(request, briefs['CUST-007'] ?? '')).at(-1);
    const behind = await request.post(
      `${apiUrl()}/api/v1/risk/briefs/${briefs['CUST-007'] ?? ''}/decision`,
      {
        data: {
          actor: 'Other Reviewer',
          decision: 'APPROVED',
          note: null,
          payload_hash: head?.payload_hash,
          supersedes_id: head?.id,
        },
      },
    );
    expect(behind.status()).toBe(201);

    const refused = decisionPosted(page);
    await form.getByRole('button', { name: 'Record decision' }).click();
    const refusal = await refused;
    expect(refusal.status()).toBe(409);
    expect(
      ((await refusal.json()) as { error: { code: string; details: { reason: string } } }).error,
    ).toMatchObject({
      code: 'DECISION_CONFLICT',
      details: { reason: 'PREDECESSOR_NOT_HEAD' },
    });
    await expect(form).toContainText('Someone recorded a decision on this brief meanwhile.');
    await expect(form.getByLabel(/^Note/)).toHaveValue('Written before the other reviewer.');
    await expect(page.getByRole('region', { name: 'Decision chain' }).getByText('③')).toBeVisible();

    const resent = decisionPosted(page);
    await form.getByRole('button', { name: 'Record decision' }).click();
    expect((await resent).status()).toBe(201);
    await expect(
      page
        .getByRole('region', { name: 'Decision chain' })
        .getByRole('link', { name: 'supersedes ③' }),
    ).toBeVisible();
    const stored = await chainOf(request, briefs['CUST-007'] ?? '');
    expect(stored.map((item) => item.actor)).toEqual([
      'E2E Owner',
      'E2E Owner',
      'Other Reviewer',
      'E2E Owner',
    ]);
  });

  test('409 PAYLOAD_HASH_CONFLICT: the brief changed; the note is kept; nothing is written', async ({
    page,
    request,
  }) => {
    const form = await openBrief(page, 'CUST-036');
    await page.route('**/api/v1/risk/briefs/*/decision', async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      await route.continue({ postData: JSON.stringify({ ...body, payload_hash: '0'.repeat(64) }) });
    });
    await decide(form, 'Approve', 'Sent with a stale hash.', 'E2E Owner');

    const refused = decisionPosted(page);
    await form.getByRole('button', { name: 'Record decision' }).click();
    const refusal = await refused;
    expect(refusal.status()).toBe(409);
    expect(
      ((await refusal.json()) as { error: { code: string; details: { reason: string } } }).error,
    ).toMatchObject({
      code: 'PAYLOAD_HASH_CONFLICT',
      details: { reason: 'REQUEST_HASH_MISMATCH' },
    });
    await expect(form).toContainText('This brief changed since you opened it.');
    await expect(form.getByLabel(/^Note/)).toHaveValue('Sent with a stale hash.');
    expect(await chainOf(request, briefs['CUST-036'] ?? '')).toEqual([]);
    await page.unroute('**/api/v1/risk/briefs/*/decision');
  });

  test("an empty chain: CUST-025's brief has no decision yet", async ({ page }) => {
    await openBrief(page, 'CUST-025');

    await expect(page.getByRole('region', { name: 'Decision chain' })).toContainText(
      'No decisions recorded for this brief yet.',
    );
    await expect(page.locator('[data-decision-status]')).toHaveAttribute(
      'data-decision-status',
      'PENDING',
    );
  });

  test('an unknown outcome that landed: the page re-reads and offers no retry (R-F-7)', async ({
    page,
    request,
  }) => {
    const form = await openBrief(page, 'CUST-025');
    await page.route('**/api/v1/risk/briefs/*/decision', async (route) => {
      await route.fetch();
      await route.abort('connectionreset');
    });
    await decide(form, 'Approve', 'Its answer is lost on the way back.', 'E2E Owner');

    await form.getByRole('button', { name: 'Record decision' }).click();

    await expect(form).toContainText('It was recorded. The chain below includes it.');
    await expect(form.getByRole('button', { name: 'Retry' })).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Decision chain' }).getByText('①')).toBeVisible();
    expect(await chainOf(request, briefs['CUST-025'] ?? '')).toHaveLength(1);
    await page.unroute('**/api/v1/risk/briefs/*/decision');
  });

  test('an unknown outcome that did not land: Retry is offered and records it once', async ({
    page,
    request,
  }) => {
    const form = await openBrief(page, 'CUST-036');
    await page.route('**/api/v1/risk/briefs/*/decision', (route) => route.abort('connectionreset'));
    await decide(form, 'Reject', 'The first attempt never arrives.', 'E2E Owner');

    await form.getByRole('button', { name: 'Record decision' }).click();

    await expect(form).toContainText('It was not recorded, so you can send it again.');
    expect(await chainOf(request, briefs['CUST-036'] ?? '')).toEqual([]);
    await page.unroute('**/api/v1/risk/briefs/*/decision');
    const posted = decisionPosted(page);
    await form.getByRole('button', { name: 'Retry' }).click();
    expect((await posted).status()).toBe(201);
    await expect(form).toContainText('Recorded: REJECTED by E2E Owner.');
    expect(await chainOf(request, briefs['CUST-036'] ?? '')).toHaveLength(1);
  });
});

test.describe('Auto, and an API that is down', () => {
  test('Auto sends as_of null; the inbox shows the snapshot at the date it resolved to', async ({
    page,
  }) => {
    await page.goto(`${baseUrl()}/classic`);
    await page.getByLabel('as_of', { exact: true }).selectOption('auto');
    await expect(page).toHaveURL(/as_of=auto/);

    const posted = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && response.url().endsWith('/risk/assessments'),
    );
    await page.getByRole('banner').getByRole('button', { name: 'Run assessment' }).click();
    const response = await posted;

    expect(response.status()).toBe(201);
    expect(response.request().postDataJSON()).toEqual({ as_of: null, source_system: 'csv_demo' });
    await expect(page.getByRole('status', { name: 'Assessment run' })).toContainText(
      'Assessed 50 customers at 2026-08-27',
    );
    await expect(page).toHaveURL(/\/classic\/inbox\?as_of=auto$/);
    await expect(await inboxRows(page)).toHaveCount(4);
    await expect(page.getByRole('main')).toContainText('as_of 2026-08-27');
  });

  test('API down: the HUD and the inbox say so, and Retry recovers once it is back', async ({
    page,
  }) => {
    await page.route('**/api/v1/**', (route) => route.abort('connectionrefused'));
    await page.goto(`${baseUrl()}/classic/inbox`);

    await expect(page.getByRole('banner')).toContainText('API unreachable', { timeout: 10_000 });
    const alert = page.getByRole('main').getByRole('alert');
    await expect(alert).toContainText('NETWORK_ERROR', { timeout: 10_000 });

    await page.unroute('**/api/v1/**');
    await alert.getByRole('button', { name: 'Retry' }).click();
    await expect(await inboxRows(page)).toHaveCount(3);
    await page.getByRole('banner').getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByTestId('health-light')).toContainText('API healthy');
  });
});

test.describe('accessibility (§10, AC-F-12)', () => {
  test('every Classic route and panel has no serious or critical axe violation', async ({
    page,
  }) => {
    const routes = [
      '/classic',
      '/classic/inbox',
      `/classic/briefs/${briefs['CUST-007'] ?? ''}`,
      ...AGENT_IDS.map((id) => `/classic/agents/${id}`),
    ];
    for (const route of routes) {
      await page.goto(`${baseUrl()}${route}`);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await page.waitForLoadState('networkidle');
      await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
      await expectAccessible(page);
    }
  });
});
