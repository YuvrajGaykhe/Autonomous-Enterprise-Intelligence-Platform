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
  testMatch: '**/*.spec.ts',
  globalSetup: './tests/e2e/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 30_000,
  reporter: [['list']],
  outputDir: 'test-results',
  // Classic routes are compared pixel-exactly within 1% (spec §12.1).
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
