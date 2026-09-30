/**
 * `npm run perf`: the performance record (spec §9.10), measured on this machine.
 *
 * It serves the production build over a freshly recreated `<database>_frontend_e2e` (R-F-1), opens
 * the office at 1920×1080 in the installed Google Chrome, and reads `?perf=1`'s own measurement
 * after 30 seconds: the median and 95th-percentile frame time and the draw calls per frame, once
 * with the pixel pass and once smooth. It prints the machine, the GPU and the numbers, and exits 1
 * when a budget is exceeded. It must not run at the same time as the end-to-end tests, which use
 * the same database.
 *
 * Every agent moves while it measures (F4): `?perf=1` keeps idle agents strolling round the Break
 * Area without a pause, and the measurement starts a Replay, so the assessment's agents walk to
 * their desks and to each other under the arrows.
 */

import { execFileSync } from 'node:child_process';
import { cpus, totalmem } from 'node:os';
import { resolve } from 'node:path';

import { chromium } from '@playwright/test';
import { preview } from 'vite';

import type { PerfSummary } from '../src/domain/perf.ts';
import { TOUR_SEEN } from '../src/domain/tour.ts';
import { STORAGE_KEYS } from '../src/lib/storage.ts';

import { E2E_SUFFIX, EnvironmentRefused, freePort, startIsolatedBackend } from './lib/isolated.ts';
import { configuredDatabaseUrl } from './lib/settings.ts';

const VIEWPORT = { width: 1920, height: 1080 };
const MEASURE_MS = 30_000;
/** Frames drawn before measuring, so start-up work is not counted. */
const WARM_UP_MS = 3_000;

/** What `?perf=1` exposes on the page (src/world/Perf.tsx). */
interface PageRecord {
  samples: unknown[];
  renderer: string;
  summary: () => PerfSummary | null;
}
type PerfWindow = Window & { aiceohqPerf?: PageRecord };

interface Measured {
  mode: string;
  renderer: string;
  summary: PerfSummary | null;
}

function machine(): string {
  let model = 'unknown model';
  try {
    model = execFileSync('sysctl', ['-n', 'hw.model'], { encoding: 'utf8' }).trim();
  } catch {
    // Not macOS: the CPU line below still names the machine.
  }
  const memory = Math.round(totalmem() / 1024 ** 3);
  return `${model}, ${cpus()[0]?.model ?? 'unknown CPU'}, ${memory} GB`;
}

async function measure(baseUrl: string, mode: 'pixel' | 'smooth'): Promise<Measured> {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
    // A returning reader: the tour (F6) stays closed, so nothing covers the office.
    await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
      STORAGE_KEYS.tour,
      TOUR_SEEN,
    ] as const);
    await page.goto(`${baseUrl}/?perf=1&pixel=${mode === 'pixel' ? '1' : '0'}`);
    await page.getByTestId('office').and(page.locator('[data-world="ready"]')).waitFor();
    await page.waitForTimeout(WARM_UP_MS);
    await page.getByRole('button', { name: 'Replay' }).click();
    await page.getByTestId('office').and(page.locator('[data-show="replay"]')).waitFor();
    await page.evaluate(() => {
      const record = (window as PerfWindow).aiceohqPerf;
      if (record) record.samples = [];
    });
    await page.waitForTimeout(MEASURE_MS);
    const replaying = await page.getByTestId('office').getAttribute('data-show');
    if (replaying !== 'replay') throw new Error(`the replay ended before the measurement did`);
    return await page.evaluate((label) => {
      const record = (window as PerfWindow).aiceohqPerf;
      return {
        mode: label,
        renderer: record?.renderer ?? 'unknown',
        summary: record?.summary() ?? null,
      };
    }, mode);
  } finally {
    await browser.close();
  }
}

async function main(): Promise<number> {
  const backend = await startIsolatedBackend({
    suffix: E2E_SUFFIX,
    configuredUrl: configuredDatabaseUrl(),
    port: 0,
    quiet: true,
  });
  process.env['FRONTEND_API_TARGET'] = backend.baseUrl;
  const port = await freePort();
  const server = await preview({
    configFile: resolve(import.meta.dirname, '../vite.config.ts'),
    preview: { port, strictPort: true },
  });
  try {
    const baseUrl = `http://127.0.0.1:${port}`;
    process.stdout.write(`[perf] machine: ${machine()}\n`);
    process.stdout.write(
      `[perf] viewport ${VIEWPORT.width}×${VIEWPORT.height} at device pixel ratio 1, ` +
        `${MEASURE_MS / 1000} s per mode\n`,
    );
    let within = true;
    for (const mode of ['pixel', 'smooth'] as const) {
      const result = await measure(baseUrl, mode);
      const summary = result.summary;
      process.stdout.write(`[perf] ${mode}: renderer ${result.renderer}\n`);
      if (summary === null) {
        process.stdout.write(`[perf] ${mode}: no frames were measured\n`);
        within = false;
        continue;
      }
      process.stdout.write(
        `[perf] ${mode}: ${summary.frames} frames over ${(summary.spanMs / 1000).toFixed(1)} s; ` +
          `frame median ${summary.medianMs.toFixed(2)} ms, p95 ${summary.p95Ms.toFixed(2)} ms; ` +
          `draw calls max ${summary.maxDrawCalls}, median ${summary.medianDrawCalls}; ` +
          `triangles max ${summary.maxTriangles}; ${summary.within ? 'within' : 'OVER'} budget\n`,
      );
      within &&= summary.within;
    }
    return within ? 0 : 1;
  } finally {
    await new Promise<void>((done) => server.httpServer.close(() => done()));
    await backend.stop();
  }
}

main().then(
  (status) => process.exit(status),
  (error: unknown) => {
    if (error instanceof EnvironmentRefused) {
      process.stderr.write(`perf-record: ${error.message}\n`);
      process.exit(2);
    }
    throw error;
  },
);
