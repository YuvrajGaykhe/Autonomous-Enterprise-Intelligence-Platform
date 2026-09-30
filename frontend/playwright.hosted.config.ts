/**
 * The hosted smoke test (spec §14 F5): the deployed site at AICEOHQ_HOSTED_URL, or `vercel dev`
 * on a loopback port to rehearse it. There is no global setup: the site brings its own database.
 * It runs only when asked, through `npm run smoke:hosted`.
 *
 * The `@clean` tests only read. The `@write` test records one approval, which `make demo-reset`
 * removes: run everything, reset, then `npm run smoke:hosted -- --grep @clean` proves the site
 * is clean again.
 */

import { defineConfig } from '@playwright/test';

const hostedUrl = process.env['AICEOHQ_HOSTED_URL'];
if (hostedUrl === undefined || !/^(https:\/\/[^/]+|http:\/\/127\.0\.0\.1:\d+)$/.test(hostedUrl))
  throw new Error('Set AICEOHQ_HOSTED_URL to the deployment, e.g. https://<name>.vercel.app');

export default defineConfig({
  testDir: 'tests/hosted',
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  // A cold start of the API's function comes first.
  timeout: 60_000,
  reporter: [['list']],
  outputDir: 'test-results/hosted',
  use: {
    baseURL: hostedUrl,
    channel: 'chrome',
    headless: true,
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 800 },
    timezoneId: 'UTC',
    locale: 'en-GB',
    colorScheme: 'light',
  },
});
