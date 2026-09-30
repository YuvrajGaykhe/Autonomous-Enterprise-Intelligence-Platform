/**
 * Playwright end-to-end tests (spec §12.1, §12.3).
 *
 * The global setup recreates `<database>_frontend_e2e`, serves the working-tree API over it on an
 * OS-assigned port and serves the production build through `vite preview` with `/api` proxied to
 * that API. Tests never run concurrently with themselves. The browser is the installed Google
 * Chrome (owner ruling, F1). The screenshot baselines therefore follow Chrome: an update to it may
 * need the baselines re-approved.
 */

import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  // The office runs first: it writes nothing, and its screenshots need the database as the global
  // setup left it, before Classic's scenario records decisions (F3). Life runs last (F4): it records
  // a decision from the office and an ingestion run, which Classic's screenshots must not see.
  projects: [
    { name: 'office', testMatch: 'office.spec.ts' },
    { name: 'classic', testMatch: ['classic.spec.ts', 'smoke.spec.ts'], dependencies: ['office'] },
    { name: 'life', testMatch: 'life.spec.ts', dependencies: ['classic'] },
  ],
  // Baselines are named by test file and platform only, as they were before there were projects.
  snapshotPathTemplate:
    '{testDir}/{testFileDir}/{testFileName}-snapshots/{arg}{-snapshotSuffix}{ext}',
  globalSetup: './tests/e2e/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 30_000,
  reporter: [['list']],
  outputDir: 'test-results',
  // Classic routes are compared pixel-exactly within 1%; the office, whose WebGL output can vary,
  // within 5% (spec §12.1).
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: 'disabled' } },
  use: {
    channel: 'chrome',
    headless: true,
    trace: 'retain-on-failure',
    // A fixed viewport, zone, locale and scheme, so screenshots and timestamps are reproducible.
    viewport: { width: 1280, height: 800 },
    timezoneId: 'UTC',
    locale: 'en-GB',
    colorScheme: 'light',
  },
});
