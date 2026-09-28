/**
 * End-to-end helpers: the servers the global setup started, the API read directly (to learn ids
 * and to check what a page wrote), and axe.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import AxeBuilder from '@axe-core/playwright';
import { expect, type APIRequestContext, type Page } from '@playwright/test';

function environment(name: string): string {
  const value = process.env[name];
  if (value === undefined) throw new Error(`${name} is not set: run through playwright test`);
  return value;
}

export const baseUrl = () => environment('AICEOHQ_E2E_BASE_URL');
export const apiUrl = () => environment('AICEOHQ_E2E_API_URL');

export const GOLDEN = readFileSync(
  resolve(import.meta.dirname, '../../../tests/golden/vs01_cust007_brief.txt'),
  'utf8',
);

export interface Decision {
  id: string;
  actor: string;
  decision: 'APPROVED' | 'REJECTED';
  note: string | null;
  supersedes_id: string | null;
  payload_hash: string;
}

/** The brief ids at 2026-09-18, by customer, read from the API itself. */
export async function briefIds(request: APIRequestContext): Promise<Record<string, string>> {
  const response = await request.get(
    `${apiUrl()}/api/v1/risk/assessments?as_of=2026-09-18&limit=500&offset=0`,
  );
  expect(response.status()).toBe(200);
  const body = (await response.json()) as {
    items: { customer_source_id: string; brief_ids: string[] }[];
  };
  return Object.fromEntries(
    body.items
      .filter((item) => item.brief_ids.length > 0)
      .map((item) => [item.customer_source_id, item.brief_ids[0] as string]),
  );
}

export async function chainOf(request: APIRequestContext, briefId: string): Promise<Decision[]> {
  const response = await request.get(`${apiUrl()}/api/v1/risk/briefs/${briefId}/decisions`);
  expect(response.status()).toBe(200);
  return ((await response.json()) as { items: Decision[] }).items;
}

export async function statusOf(request: APIRequestContext, briefId: string): Promise<string> {
  const response = await request.get(`${apiUrl()}/api/v1/risk/briefs/${briefId}`);
  return ((await response.json()) as { decision_status: string }).decision_status;
}

/** Axe on the current page: no serious and no critical violation (spec §10). */
export async function expectAccessible(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations
    .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
    .map(
      (violation) =>
        `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`,
    );
  expect(blocking).toEqual([]);
}

/** Wait for the fonts, so screenshots are taken with the final glyphs. */
export async function fontsReady(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}
