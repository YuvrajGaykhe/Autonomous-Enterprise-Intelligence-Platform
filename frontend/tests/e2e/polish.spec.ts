/**
 * F6's gate (spec §14 F6, AC-F-7, AC-F-12): the three-step tour over the real office, and phones
 * sent to Classic view, against the real API over the isolated `<database>_frontend_e2e`.
 *
 * It runs with the office project, before Classic's scenario writes decisions, because its phone
 * screenshot needs the clean database. It writes nothing but browser storage.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, type Page } from '@playwright/test';

import { TOUR_SEEN } from '../../src/domain/tour';
import { STORAGE_KEYS } from '../../src/lib/storage';

import { baseUrl, briefIds, expectAccessible, fontsReady, test } from './support';

test.describe.configure({ mode: 'serial' });

let briefs: Record<string, string>;

test.beforeAll(async ({ request }) => {
  briefs = await briefIds(request);
});

const PHONE = { width: 375, height: 812 };

/** The scripts `index.html` loads: everything Classic view may ever request. */
function initialScripts(): Set<string> {
  const html = readFileSync(resolve(import.meta.dirname, '../../dist/index.html'), 'utf8');
  return new Set(
    [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.js)"/g)].map((match) => match[1] ?? ''),
  );
}

/** What the open tour rings: one element, described by its label or its text. */
async function spot(page: Page): Promise<string[]> {
  return page
    .locator('[data-tour-spot="on"]')
    .evaluateAll((elements) =>
      elements.map((element) => element.getAttribute('aria-label') ?? element.textContent ?? ''),
    );
}

test.describe('the tour (§8.2)', () => {
  test.use({ tourSeen: false });

  test('opens over the office on a first visit and walks through three steps', async ({ page }) => {
    await page.goto(`${baseUrl()}/`);
    const tour = page.getByTestId('tour');
    await expect(tour.getByRole('heading', { name: 'Meet the agents' })).toBeVisible();
    await expect(page.getByTestId('office')).toHaveAttribute('data-world', 'ready', {
      timeout: 15_000,
    });
    expect(await spot(page)).toEqual(['Staff directory']);
    await expect(tour.getByRole('button', { name: 'Next' })).toBeFocused();
    await expectAccessible(page);

    await tour.getByRole('button', { name: 'Next' }).click();
    await expect(tour.getByRole('heading', { name: 'Watch a run' })).toBeVisible();
    expect(await spot(page)).toEqual(['ReplayRun assessment']);

    await tour.getByRole('button', { name: 'Next' }).click();
    await expect(tour.getByRole('heading', { name: 'Decide as the CEO' })).toBeVisible();
    expect(await spot(page)).toEqual(['CEO inbox']);
    await expectAccessible(page);

    await tour.getByRole('button', { name: 'Start exploring' }).click();
    await expect(tour).toBeHidden();
    expect(await spot(page)).toEqual([]);
    expect(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.tour)).toBe(
      TOUR_SEEN,
    );

    await page.reload();
    await expect(page.getByTestId('office')).toHaveAttribute('data-world', 'ready', {
      timeout: 15_000,
    });
    await expect(tour).toBeHidden();

    await page.getByRole('button', { name: 'Tour' }).click();
    await expect(tour.getByRole('heading', { name: 'Meet the agents' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(tour).toBeHidden();
    await expect(page.getByRole('button', { name: 'Tour' })).toBeFocused();
  });

  test('waits on a deep link, where the reader came for something else', async ({ page }) => {
    await page.goto(`${baseUrl()}/classic/briefs/${briefs['CUST-007'] ?? ''}`);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByTestId('tour')).toBeHidden();
  });
});

test.describe('phones get Classic view (§14 F6)', () => {
  test.use({ viewport: PHONE });

  const notice = /The 3D office needs a window at least 768 pixels wide/;

  test('the office sends a phone to its Classic twin, without the world chunk', async ({
    page,
  }) => {
    const scripts: string[] = [];
    page.on('request', (request) => {
      if (request.resourceType() === 'script') scripts.push(new URL(request.url()).pathname);
    });

    await page.goto(`${baseUrl()}/?agent=linker&as_of=2026-09-18`);

    await expect(page).toHaveURL(`${baseUrl()}/classic/agents/linker?as_of=2026-09-18`);
    await expect(page.getByRole('status').filter({ hasText: notice })).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toContainText('LINKER_AGENT');
    const views = page.getByRole('navigation', { name: 'View' });
    await expect(views.getByRole('link', { name: 'Office' })).toHaveCount(0);
    await expect(views.locator('[aria-disabled="true"]')).toHaveText(
      'Office (needs a wider window)',
    );
    await page.waitForLoadState('networkidle');
    const initial = initialScripts();
    expect(scripts.filter((script) => !initial.has(script))).toEqual([]);
  });

  test('every Classic page fits the phone, with no sideways scroll, and passes axe', async ({
    page,
  }) => {
    const paths = [
      '/classic',
      '/classic/inbox',
      ...['CUST-007', 'CUST-025', 'CUST-036'].map((id) => `/classic/briefs/${briefs[id] ?? ''}`),
      ...['csv_demo', 'odoo_mock', 'memory', 'linker', 'signals', 'sales', 'support'].map(
        (id) => `/classic/agents/${id}`,
      ),
      ...['reconciler', 'brief-writer', 'ceo'].map((id) => `/classic/agents/${id}`),
    ];
    for (const path of paths) {
      await page.goto(`${baseUrl()}${path}?as_of=2026-09-18`);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await page.waitForLoadState('networkidle');
      // Every "Show the API call" open, so its table is measured too.
      await page.locator('details').evaluateAll((all) => {
        for (const details of all) (details as HTMLDetailsElement).open = true;
      });
      const widths = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
      }));
      expect(widths.scroll, path).toBeLessThanOrEqual(widths.client);
      await expectAccessible(page);
    }
  });

  test('the inbox on a phone', async ({ page }) => {
    await page.goto(`${baseUrl()}/classic/inbox?as_of=2026-09-18`);
    await expect(page.getByRole('link', { name: /CUST-036/ })).toBeVisible();
    await fontsReady(page);
    await expect(page).toHaveScreenshot('phone-inbox.png', { fullPage: true });
  });

  test('the tour fits a phone too', async ({ browser }) => {
    const context = await browser.newContext({ viewport: PHONE });
    try {
      const page = await context.newPage();
      await page.goto(`${baseUrl()}/`);
      await expect(page).toHaveURL(`${baseUrl()}/classic`);
      const tour = page.getByTestId('tour');
      await expect(tour.getByRole('heading', { name: 'Meet the agents' })).toBeVisible();
      const box = await tour.boundingBox();
      expect(box?.x).toBeGreaterThanOrEqual(0);
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(PHONE.width);
      expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(PHONE.height);
      expect(await spot(page)).toEqual(['Staff directory']);
      await expectAccessible(page);
    } finally {
      await context.close();
    }
  });
});

test.describe('the office starts at 768 pixels', () => {
  test('768 wide gets the office; 767 wide gets Classic view', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 800 });
    await page.goto(`${baseUrl()}/`);
    await expect(page.getByTestId('office')).toHaveAttribute('data-world', 'ready', {
      timeout: 15_000,
    });

    await page.setViewportSize({ width: 767, height: 800 });
    await expect(page).toHaveURL(`${baseUrl()}/classic`);
    await expect(page.getByText(/needs a window at least 768 pixels wide/)).toBeVisible();
  });
});
