/**
 * F3's gate (spec §14, AC-F-7, AC-F-8, AC-F-12): the 3D office against the real API over the
 * isolated `<database>_frontend_e2e`, drawn by the installed Chrome's real WebGL.
 *
 * This file runs before Classic's scenario (playwright.config.ts), while the database is as the
 * global setup left it: assessed at 2026-09-18, no decision recorded. It writes nothing, so
 * Classic's own screenshots still see that state.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, test, type Locator, type Page } from '@playwright/test';

import { COPY } from '../../src/copy';

import { apiUrl, baseUrl, briefIds, expectAccessible, fontsReady } from './support';

test.describe.configure({ mode: 'serial' });

let briefs: Record<string, string>;

test.beforeAll(async ({ request }) => {
  briefs = await briefIds(request);
});

/** The scripts `index.html` loads: everything Classic view may ever request. */
function initialScripts(): Set<string> {
  const html = readFileSync(resolve(import.meta.dirname, '../../dist/index.html'), 'utf8');
  return new Set(
    [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.js)"/g)].map((match) => match[1] ?? ''),
  );
}

function office(page: Page): Locator {
  return page.getByTestId('office');
}

/** Open the office and wait until its world has drawn and its data has arrived. */
async function openOffice(page: Page, query = ''): Promise<Locator> {
  await page.goto(`${baseUrl()}/${query}`);
  const root = office(page);
  await expect(root).toHaveAttribute('data-world', 'ready', { timeout: 15_000 });
  // CSS, not roles: an open panel is modal, which hides the page behind it from the role tree.
  const directory = page.locator('nav[aria-label="Staff directory"]');
  await expect(directory.locator('[data-agent="ceo"]')).toContainText(
    '3 briefs await your decision',
  );
  await expect(directory.locator('[data-agent="rest_mock"]')).toBeVisible();
  await expect(page.locator(`section[aria-label="SIGNALS_AGENT's board"]`)).toContainText(
    'BAND CRITICAL',
  );
  return root;
}

/** Wait for the fonts and a few frames, so the board is drawn with its face and labels settle. */
async function settle(page: Page): Promise<void> {
  await fontsReady(page);
  await page.evaluate(
    () =>
      new Promise<void>((done) => {
        let frames = 0;
        const next = () => (++frames >= 10 ? done() : requestAnimationFrame(next));
        requestAnimationFrame(next);
      }),
  );
}

/** How many distinct colours a screenshot of the canvas holds: a blank canvas has one. */
async function canvasColours(page: Page): Promise<number> {
  const png = await page.locator('canvas').screenshot();
  return page.evaluate(async (data) => {
    const image = new Image();
    image.src = `data:image/png;base64,${data}`;
    await image.decode();
    const canvas = new OffscreenCanvas(image.width, image.height);
    const context = canvas.getContext('2d');
    if (context === null) return 0;
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, image.width, image.height).data;
    const colours = new Set<number>();
    for (let index = 0; index < pixels.length; index += 4 * 7) {
      colours.add((pixels[index]! << 16) | (pixels[index + 1]! << 8) | pixels[index + 2]!);
    }
    return colours.size;
  }, png.toString('base64'));
}

/** The centre of a label's element, in page coordinates. */
async function labelCentre(page: Page, id: string): Promise<{ x: number; y: number }> {
  const box = await page.locator(`[data-label="${id}"] > div`).boundingBox();
  if (box === null) throw new Error(`label ${id} is not on screen`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

test.describe('screenshots at ?still=1 (§12.1)', () => {
  test('the office, in pixel art and in smooth toon', async ({ page }) => {
    const root = await openOffice(page, '?still=1');
    await expect(root).toHaveAttribute('data-pixel', '1');
    await settle(page);
    expect(await canvasColours(page)).toBeGreaterThan(40);
    await expect(page).toHaveScreenshot('office-pixel.png', { maxDiffPixelRatio: 0.05 });

    await page
      .getByRole('group', { name: 'Rendering' })
      .getByRole('button', { name: 'Smooth' })
      .click();
    await expect(root).toHaveAttribute('data-pixel', '0');
    await settle(page);
    expect(await canvasColours(page)).toBeGreaterThan(40);
    await expect(page).toHaveScreenshot('office-smooth.png', { maxDiffPixelRatio: 0.05 });
  });

  test('the office turned and zoomed in, over the Signals Desk and the CEO corner', async ({
    page,
  }) => {
    const root = await openOffice(page, '?still=1&pixel=0');
    const controls = page.getByRole('toolbar', { name: 'View controls' });
    await controls.getByRole('button', { name: 'Turn right (E)' }).click();
    await controls.getByRole('button', { name: 'Zoom in (plus)' }).click();
    await controls.getByRole('button', { name: 'Zoom in (plus)' }).click();
    await expect(root).toHaveAttribute('data-yaw', '135');
    await expect(root).toHaveAttribute('data-zoom', '2');
    for (let step = 0; step < 4; step += 1) await page.keyboard.press('ArrowDown');
    await settle(page);
    await expect(page).toHaveScreenshot('office-turned.png', { maxDiffPixelRatio: 0.05 });
  });
});

test.describe('the world chunk (§9.10, AC-F-7)', () => {
  test('Classic view never downloads it; the office does', async ({ page }) => {
    const initial = initialScripts();
    const scripts: string[] = [];
    page.on('request', (request) => {
      if (request.resourceType() === 'script') scripts.push(new URL(request.url()).pathname);
    });

    const classic = [
      '/classic',
      '/classic/inbox',
      `/classic/briefs/${briefs['CUST-007'] ?? ''}`,
      '/classic/agents/signals',
      '/classic/agents/csv_demo',
    ];
    for (const path of classic) {
      await page.goto(`${baseUrl()}${path}`);
      await expect(page.getByRole('main')).toBeVisible();
      await page.waitForLoadState('networkidle');
    }
    expect(scripts.length).toBeGreaterThan(0);
    expect(scripts.filter((script) => !initial.has(script))).toEqual([]);

    await openOffice(page);
    const lazy = scripts.filter((script) => !initial.has(script));
    expect(lazy.length).toBeGreaterThan(0);
    expect(lazy.every((script) => /\/assets\/Office-[\w-]+\.js$/.test(script))).toBe(true);
  });
});

test.describe('the office (§8, §9)', () => {
  test("shows each agent's state in its tag and in the staff directory", async ({ page }) => {
    await openOffice(page);
    const directory = page.getByRole('navigation', { name: 'Staff directory' });

    await expect(directory.getByRole('link', { name: /^CSV_DEMO_AGENT/ })).toContainText('Idle');
    await expect(directory.getByRole('link', { name: /^ODOO_MOCK_AGENT/ })).toContainText(
      'Its source reports unhealthy.',
    );
    await expect(page.locator('[data-agent-tag="odoo_mock"] [data-bulb]')).toHaveAttribute(
      'data-bulb',
      'error',
    );
    await expect(page.locator('[data-agent-tag="ceo"] [data-bulb]')).toHaveAttribute(
      'data-bulb',
      'waiting',
    );
    await expect(page.locator('[data-bubble="waiting"]')).toHaveText('?');
    for (const room of ['pipeline-room', 'account-360', 'war-room', 'copilot-desk']) {
      await expect(page.locator(`[data-room="${room}"]`)).toContainText(/Opens with VS-0[2-5]/);
    }
  });

  test("draws SIGNALS_AGENT's board from CUST-007's assessment", async ({ page, request }) => {
    await openOffice(page);
    const list = await request.get(
      `${apiUrl()}/api/v1/risk/assessments?as_of=2026-09-18&limit=500&offset=0`,
    );
    const items = ((await list.json()) as { items: { id: string; customer_source_id: string }[] })
      .items;
    const assessment = items.find((item) => item.customer_source_id === 'CUST-007');
    const detail = (await (
      await request.get(`${apiUrl()}/api/v1/risk/assessments/${assessment?.id ?? ''}`)
    ).json()) as { signals: Record<string, unknown> };

    const board = page.getByRole('region', { name: "SIGNALS_AGENT's board" });
    await expect(board).toContainText('SIGNALS CUST-007');
    for (const [id, key] of [
      ['S1', 'open_ticket_count'],
      ['S7', 'sla_breach_count'],
      ['S10', 'dominant_ticket_category'],
    ] as const) {
      await expect(board).toContainText(`${id} ${key}: ${String(detail.signals[key])}`);
    }
  });

  test('opens a panel from the staff directory, traps focus and returns it', async ({ page }) => {
    await openOffice(page);
    const entry = page
      .getByRole('navigation', { name: 'Staff directory' })
      .getByRole('link', { name: /^MEMORY/ });
    await entry.focus();
    await page.keyboard.press('Enter');

    await expect(page).toHaveURL(/\/\?agent=memory$/);
    const drawer = page.getByRole('dialog', { name: 'MEMORY' });
    await expect(drawer.getByRole('region', { name: 'Ingestion metrics' })).toContainText('233');
    await expectAccessible(page);
    for (let step = 0; step < 12; step += 1) await page.keyboard.press('Tab');
    await expect(drawer.locator(':focus')).toHaveCount(1);

    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(entry).toBeFocused();
  });

  test('opens panels from the world: a name tag and a click on an agent', async ({ page }) => {
    await openOffice(page, '?still=1');

    await page.locator('[data-agent-tag="linker"]').click();
    await expect(page.getByRole('dialog', { name: 'LINKER_AGENT' })).toBeVisible();
    await page.keyboard.press('Escape');

    const memory = await labelCentre(page, 'tag:memory');
    await page.mouse.click(memory.x, memory.y + 30);
    await expect(page.getByRole('dialog', { name: 'MEMORY' })).toBeVisible();
    await expect(page).toHaveURL(/\?still=1&agent=memory$/);
    await page.keyboard.press('Escape');

    const ceo = await labelCentre(page, 'tag:ceo');
    await page.mouse.click(ceo.x, ceo.y + 40);
    await expect(page.getByRole('dialog', { name: 'CEO inbox' })).toBeVisible();
  });

  test('opens the inbox, then a brief over the office, each accessible', async ({ page }) => {
    await openOffice(page, '?inbox=1');
    const inbox = page.getByRole('dialog', { name: 'CEO inbox' });
    const rows = inbox.getByTestId('inbox-row');
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText('CRITICAL·EXECUTIVE');
    await expect(rows.nth(0)).toContainText('CUST-007');
    await expectAccessible(page);

    await rows.nth(0).click();
    await expect(page).toHaveURL(new RegExp(`/brief/${briefs['CUST-007'] ?? ''}$`));
    const overlay = page.getByRole('dialog', { name: 'Brief' });
    await expect(overlay.getByRole('region', { name: 'Technical' })).toBeVisible();
    await expect(overlay.getByRole('region', { name: 'Decision chain' })).toContainText(
      COPY.emptyDecisionChain,
    );
    await expectAccessible(page);

    await overlay
      .getByRole('region', { name: 'Evidence: tickets' })
      .getByRole('button', { name: /created_at$/ })
      .first()
      .click();
    await expect(office(page)).toHaveAttribute('data-highlight', 'support');
    await page.keyboard.press('Escape');
    await page.keyboard.press('Escape');
    await expect(page).toHaveURL(`${baseUrl()}/`);
  });

  test('switches to Classic and back, keeping the address and remembering the choice', async ({
    page,
  }) => {
    await openOffice(page, '?as_of=2026-09-18');
    const views = page.getByRole('navigation', { name: 'View' });
    await views.getByRole('link', { name: 'Classic' }).click();
    await expect(page).toHaveURL(`${baseUrl()}/classic?as_of=2026-09-18`);

    await page.goto(`${baseUrl()}/?agent=linker`);
    await expect(page).toHaveURL(`${baseUrl()}/classic/agents/linker`);
    await expect(page.getByText(COPY.webglFallback)).toHaveCount(0);

    await page
      .getByRole('navigation', { name: 'View' })
      .getByRole('link', { name: 'Office' })
      .click();
    await expect(page).toHaveURL(`${baseUrl()}/?agent=linker`);
    await expect(page.getByRole('dialog', { name: 'LINKER_AGENT' })).toBeVisible();
  });
});

test.describe('the WebGL fallback (§9.11, AC-F-8)', () => {
  test('a device without WebGL gets the Classic twin, with the notice', async ({ page }) => {
    await page.addInitScript(() => {
      // The page's own canvases keep their 2D context; only WebGL is refused.
      const original = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, 'getContext')
        ?.value as (...args: unknown[]) => unknown;
      Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
        value(this: HTMLCanvasElement, kind: string, ...rest: unknown[]): unknown {
          if (kind === 'webgl2' || kind === 'webgl') return null;
          return Reflect.apply(original, this, [kind, ...rest]);
        },
      });
    });
    const scripts: string[] = [];
    page.on('request', (request) => {
      if (request.resourceType() === 'script') scripts.push(new URL(request.url()).pathname);
    });

    await page.goto(`${baseUrl()}/?agent=linker&as_of=2026-09-18`);

    await expect(page).toHaveURL(`${baseUrl()}/classic/agents/linker?as_of=2026-09-18`);
    await expect(page.getByRole('status').filter({ hasText: COPY.webglFallback })).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toContainText('LINKER_AGENT');
    const initial = initialScripts();
    expect(scripts.filter((script) => !initial.has(script))).toEqual([]);
  });

  test('a context lost once is survived; lost twice, the office falls back', async ({ page }) => {
    await openOffice(page);
    const lose = () =>
      page.evaluate(() => {
        const context = document.querySelector('canvas')?.getContext('webgl2');
        const extension = context?.getExtension('WEBGL_lose_context');
        extension?.loseContext();
        return new Promise<void>((done) =>
          setTimeout(() => {
            extension?.restoreContext();
            done();
          }, 300),
        );
      });

    await lose();
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(`${baseUrl()}/`);
    await expect(office(page)).toBeVisible();

    await lose();
    await expect(page).toHaveURL(`${baseUrl()}/classic`);
    await expect(page.getByRole('status').filter({ hasText: COPY.webglFallback })).toBeVisible();
  });
});
