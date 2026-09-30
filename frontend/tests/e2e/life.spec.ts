/**
 * F4's gate (spec §14, AC-F-2, §9.4–§9.7, §9.11, R-F-6; the owner's F4 ruling): the office alive,
 * against the real API over the isolated `<database>_frontend_e2e`, drawn by the installed
 * Chrome's real WebGL.
 *
 * Agents not at work are in the Break Area. Run assessment works live, then replays the recorded
 * results under its banner: agents walk to their desks, hand their results to the next stage, meet
 * at the debate table, and BRIEF_WRITER fills the CEO's tray, three briefs at 2026-09-18. Then the
 * CEO approves from the office, and the stamp lands. This project runs last: it records a decision
 * and an ingestion run.
 */

import { expect, test, type Locator, type Page } from '@playwright/test';

import { COPY, fill } from '../../src/copy';

import { baseUrl, briefIds, chainOf, expectAccessible } from './support';

test.describe.configure({ mode: 'serial' });

let briefs: Record<string, string>;

test.beforeAll(async ({ request }) => {
  briefs = await briefIds(request);
});

function office(page: Page): Locator {
  return page.getByTestId('office');
}

async function openOffice(page: Page, query = '?as_of=2026-09-18'): Promise<Locator> {
  await page.goto(`${baseUrl()}/${query}`);
  const root = office(page);
  await expect(root).toHaveAttribute('data-world', 'ready', { timeout: 15_000 });
  await expect(root).toHaveAttribute('data-tray', '3');
  return root;
}

/** The centre of a label on the page. */
async function centre(page: Page, id: string): Promise<{ x: number; y: number }> {
  const box = await page.locator(`[data-label="${id}"] > div`).boundingBox();
  if (box === null) throw new Error(`label ${id} is not on screen`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

const distance = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.hypot(a.x - b.x, a.y - b.y);

/** The agents with a body: every one but the CEO. */
const BODIES = ['csv_demo', 'memory', 'linker', 'signals', 'sales', 'support', 'reconciler'];

function replayBanner(page: Page): Locator {
  return page.getByRole('status', { name: 'Replay' });
}

test.describe('the Break Area (the owner’s F4 ruling, §9.7)', () => {
  test('holds every agent not at work, with a smaller tag', async ({ page }) => {
    await openOffice(page, '?as_of=2026-09-18&still=1');
    await expect(office(page)).toHaveAttribute('data-show', 'none');
    const sign = await centre(page, 'room:break-area');
    const dock = await centre(page, 'room:data-dock');
    for (const id of BODIES) {
      await expect(page.locator(`[data-agent-tag="${id}"]`)).toHaveAttribute(
        'data-resting',
        'true',
      );
      const tag = await centre(page, `tag:${id}`);
      // Nearer the Break Area's sign than the Data Dock's, which is across the office.
      expect(distance(tag, sign)).toBeLessThan(distance(tag, dock));
    }
  });

  test('keeps them strolling from place to place', async ({ page }) => {
    await openOffice(page);
    const ids = BODIES;
    const before = await Promise.all(ids.map((id) => centre(page, `tag:${id}`)));
    await page.waitForTimeout(20_000);
    const after = await Promise.all(ids.map((id) => centre(page, `tag:${id}`)));
    const moved = ids.filter((_, index) => distance(before[index]!, after[index]!) > 4);
    expect(moved.length).toBeGreaterThan(0);
  });
});

test.describe('Run assessment in the office (§9.5, §9.6, AC-F-2)', () => {
  test('replays the recorded results: desks, hand-offs, the debate, three briefs in the tray', async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const root = await openOffice(page);
    await page.getByRole('button', { name: 'Run assessment' }).click();

    // The database was assessed at 2026-09-18 by the global setup: the API answers 200.
    await expect(replayBanner(page)).toHaveText(COPY.alreadyAssessedBanner, { timeout: 15_000 });
    await expect(root).toHaveAttribute('data-show', 'replay');
    await expect(root).toHaveAttribute('data-tray', '0');
    await expectAccessible(page);

    // Everyone in the episode walks from the Break Area to their desk.
    const dock = await centre(page, 'room:data-dock');
    await expect
      .poll(async () => distance(await centre(page, 'tag:memory'), dock), { timeout: 20_000 })
      .toBeLessThan(120);

    // MEMORY works at its desk, then walks its snapshot to LINKER_AGENT under a cyan arrow.
    await expect(page.locator('[data-agent-tag="memory"] [data-bulb]')).toHaveAttribute(
      'data-bulb',
      'working',
      { timeout: 20_000 },
    );
    await expect(page.locator('[data-label^="bubble:memory"] [data-bubble="caption"]')).toHaveText(
      /^SNAPSHOT [0-9a-f]{8}$/,
    );
    await expect(page.locator('[data-arrow="handoff"]').first()).toHaveText(
      /^SNAPSHOT [0-9a-f]{8}$/,
      { timeout: 10_000 },
    );

    // The analysts meet at the debate table, a red arrow between them.
    await expect(page.locator('[data-arrow="conflict"]')).toHaveText('CONFLICT DEAL-001', {
      timeout: 60_000,
    });
    await expect(
      page.locator('[data-label^="bubble:reconciler"] [data-bubble="caption"]'),
    ).toHaveText('CONF-001 → SUPPORT PREVAILS', { timeout: 15_000 });

    // BRIEF_WRITER carries the briefs to the CEO's tray, one sheet per inbox row.
    await expect(root).toHaveAttribute('data-tray', '1', { timeout: 30_000 });
    await expect(root).toHaveAttribute('data-tray', '3', { timeout: 10_000 });

    // Then the show ends and everyone goes back to the Break Area.
    await expect(root).toHaveAttribute('data-show', 'none', { timeout: 20_000 });
    await expect(replayBanner(page)).toHaveCount(0);
    for (const id of BODIES.slice(1))
      await expect(page.locator(`[data-agent-tag="${id}"]`)).toHaveAttribute(
        'data-resting',
        'true',
      );
  });

  test('then the CEO approves from the office, and the stamp lands', async ({ page, request }) => {
    const root = await openOffice(page);
    const before = await chainOf(request, briefs['CUST-007'] ?? '');

    await page.locator('[data-agent-tag="ceo"]').click();
    const inbox = page.getByRole('dialog', { name: 'CEO inbox' });
    await expect(inbox.getByTestId('inbox-row')).toHaveCount(3);
    await inbox.getByTestId('inbox-row').first().click();
    const overlay = page.getByRole('dialog', { name: 'Brief' });
    const form = overlay.getByRole('form', { name: 'Record a decision' });
    await form.getByText('Approve', { exact: true }).click();
    await form.getByLabel(/Your name/).fill('Office E2E');
    await form.getByLabel(/Note/).fill('Approved from the office.');
    await form.getByRole('button', { name: 'Record decision' }).click();

    await expect(root).toHaveAttribute('data-stamp', 'APPROVED', { timeout: 10_000 });
    const after = await chainOf(request, briefs['CUST-007'] ?? '');
    expect(after).toHaveLength(before.length + 1);
    expect(after.at(-1)).toMatchObject({ actor: 'Office E2E', decision: 'APPROVED' });
    await page.keyboard.press('Escape');
    await expect(page.locator('section[aria-label="The CEO\'s corkboard"]')).toContainText(
      `Decision ${after.length}: APPROVED`,
    );
  });
});

test.describe('Replay (§8.2, §9.6)', () => {
  test('replays the shown snapshot under its banner, and dismissing it ends the replay', async ({
    page,
  }) => {
    const root = await openOffice(page);
    await page.getByRole('button', { name: 'Replay' }).click();
    await expect(replayBanner(page)).toHaveText(fill(COPY.replayBanner, { date: '2026-09-18' }));
    await expect(root).toHaveAttribute('data-show', 'replay');
    await page.getByRole('button', { name: 'End the replay' }).click();
    await expect(root).toHaveAttribute('data-show', 'none');
    await expect(replayBanner(page)).toHaveCount(0);
  });

  test('places agents at once under reduced motion (§9.11)', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await openOffice(page);
    const dock = await centre(page, 'room:data-dock');
    await page.getByRole('button', { name: 'Replay' }).click();
    await expect(replayBanner(page)).toBeVisible();
    // No walk: MEMORY is at its desk within a moment, not after a stroll across the office.
    await expect
      .poll(async () => distance(await centre(page, 'tag:memory'), dock), { timeout: 3_000 })
      .toBeLessThan(120);
  });
});

test.describe('Run ingestion (R-F-6, §9.5)', () => {
  test('ingests from the connector’s panel, then CSV_DEMO_AGENT carries the outcome to MEMORY', async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const root = await openOffice(page, '?as_of=2026-09-18&agent=csv_demo');
    const drawer = page.getByRole('dialog', { name: 'CSV_DEMO_AGENT' });
    const section = drawer.getByRole('region', { name: 'Run ingestion' });
    await section.getByRole('button', { name: 'Run ingestion' }).click();
    const outcome = section.getByRole('status', { name: 'Ingestion run' });
    await expect(outcome).toContainText('finished NOOP', { timeout: 20_000 });
    await expect(outcome).toContainText('so nothing changed.');
    await expectAccessible(page);
    await page.keyboard.press('Escape');

    await expect(root).toHaveAttribute('data-show', 'replay');
    await expect(replayBanner(page)).toContainText('Replay of recorded results · as_of ');
    await expect(page.locator('[data-arrow="handoff"]').first()).toHaveText(
      /^NOOP · \d+ FETCHED$/,
      { timeout: 30_000 },
    );
    await expect(page.locator('[data-label^="bubble:memory"] [data-bubble="caption"]')).toHaveText(
      /^[A-Z_]+: \d+ NEW · \d+ UPDATED · \d+ UNCHANGED/,
      { timeout: 15_000 },
    );
    await expect(root).toHaveAttribute('data-show', 'none', { timeout: 40_000 });
  });

  test('is not offered for an unhealthy source', async ({ page }) => {
    await openOffice(page, '?as_of=2026-09-18&agent=odoo_mock');
    const section = page
      .getByRole('dialog', { name: 'ODOO_MOCK_AGENT' })
      .getByRole('region', { name: 'Run ingestion' });
    await expect(section.getByRole('button', { name: 'Run ingestion' })).toBeDisabled();
  });
});
